"""Crash-safe autosave and recovery for MUTT.

The manager writes the current session state to a JSON file on a background
thread whenever the UI reports a change. Writes are atomic (temp file + os.replace)
so a hard kill, segfault, or power loss never leaves a torn file behind.
On startup, :meth:`find_recoverable_sessions` scans for autosave files whose
owning process is no longer alive and offers them back to the user.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_LOG = logging.getLogger("MUTT.autosave")

AUTOSAVE_SCHEMA_VERSION = 1
_DEFAULT_DEBOUNCE_SECONDS = 0.3
_DEFAULT_PERIODIC_SECONDS = 30.0
_MAX_AUTOSAVE_BYTES = 50 * 1024 * 1024  # 50 MiB safety cap for recovery reads.
_SESSION_ID_RE = re.compile(r"^[0-9A-Za-z._-]{1,64}$")
_SHUTDOWN_SENTINEL = object()


def default_autosave_dir() -> Path:
    """Return ``~/.mutt/autosave`` (created if missing)."""
    root = Path.home() / ".mutt" / "autosave"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _is_pid_alive(pid: int) -> bool:
    """Cross-platform best-effort ``kill -0`` style liveness check."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                ok = ctypes.windll.kernel32.GetExitCodeProcess(
                    handle, ctypes.byref(exit_code)
                )
                STILL_ACTIVE = 259
                return bool(ok) and exit_code.value == STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but belongs to another user. Treat as alive.
        return True
    except OSError:
        return False
    return True


@dataclass
class RecoverableSession:
    """A previous session whose autosave file is available for recovery."""

    path: Path
    session_id: str
    timestamp: datetime
    pid: int
    original_file: Optional[str]
    file_type: Optional[str]
    data: Dict[str, Any] = field(default_factory=dict)


class AutosaveManager:
    """Coordinate debounced, crash-safe state snapshots.

    Parameters
    ----------
    snapshot_fn:
        Callable returning the full state dict to serialise. The callable must
        be safe to invoke from the worker thread (make a deep copy of wx state
        before handing it over).
    autosave_dir:
        Override the directory used for autosave files. Defaults to
        ``~/.mutt/autosave``.
    debounce_seconds:
        Minimum time between two writes triggered by rapid state changes.
    periodic_seconds:
        Even without changes, re-flush every N seconds so the timestamp stays
        fresh and the process-alive check keeps working.
    ring_size:
        Number of historical autosave files to retain per session (for
        resilience against a partially corrupted latest file).
    """

    def __init__(
        self,
        snapshot_fn: Callable[[], Optional[Dict[str, Any]]],
        *,
        autosave_dir: Optional[Path] = None,
        debounce_seconds: float = _DEFAULT_DEBOUNCE_SECONDS,
        periodic_seconds: float = _DEFAULT_PERIODIC_SECONDS,
        ring_size: int = 5,
        session_id: Optional[str] = None,
    ) -> None:
        self._snapshot_fn = snapshot_fn
        self._autosave_dir = autosave_dir or default_autosave_dir()
        self._debounce = max(0.0, debounce_seconds)
        self._periodic = max(1.0, periodic_seconds)
        self._ring_size = max(1, ring_size)
        self._session_id = session_id or self._new_session_id()
        self._pid = os.getpid()

        self._queue: "queue.Queue[Any]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last_write_ts: float = 0.0
        self._started = False

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="MUTT-Autosave", daemon=True
        )
        self._thread.start()

    def stop(self, *, flush: bool = True, delete: bool = False) -> None:
        """Stop the worker thread. Optionally flush and delete the file."""
        if not self._started:
            return
        if flush:
            try:
                self._write_once(blocking=True)
            except Exception as exc:  # noqa: BLE001
                _LOG.warning("Autosave flush failed: %s", exc)
        self._stop.set()
        self._queue.put(_SHUTDOWN_SENTINEL)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._started = False
        if delete:
            self._delete_current_file()

    # ------------------------------------------------------------ public API
    def request_save(self, snapshot: Optional[Dict[str, Any]] = None) -> None:
        """Enqueue a (debounced) write.

        Safe to call from any thread. When ``snapshot`` is provided, it is
        used verbatim (caller is responsible for thread-safety — typically
        the UI thread builds a defensive copy before calling). When omitted,
        the worker thread invokes ``snapshot_fn`` itself; this is only safe
        if the snapshot callback is internally synchronised.
        """
        if not self._started:
            return
        if snapshot is not None:
            # Copy defensively so the caller can keep mutating after the call.
            self._queue.put(("snapshot", dict(snapshot)))
        else:
            self._queue.put("save")

    def autosave_path(self) -> Path:
        return self._autosave_dir / f"{self._session_id}.autosave.json"

    def find_recoverable_sessions(
        self, *, stale_after_seconds: float = 300.0
    ) -> List[RecoverableSession]:
        """Return autosave files worth offering the user at startup."""
        results: List[RecoverableSession] = []
        now = time.time()
        for path in sorted(self._autosave_dir.glob("*.autosave.json")):
            # Skip our own session's file.
            if path.name.startswith(f"{self._session_id}."):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            # Hard size cap — refuse to json.load a huge or malicious file.
            if stat.st_size > _MAX_AUTOSAVE_BYTES:
                _LOG.warning(
                    "Autosave file %s exceeds %d bytes; skipping.",
                    path,
                    _MAX_AUTOSAVE_BYTES,
                )
                continue
            try:
                with path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                _LOG.debug("Skipping unreadable autosave %s: %s", path, exc)
                continue
            if not isinstance(data, dict):
                continue
            pid_raw = data.get("pid")
            try:
                pid = int(pid_raw) if pid_raw is not None else 0
            except (TypeError, ValueError):
                pid = 0
            ts_raw = data.get("timestamp") or ""
            try:
                ts = datetime.fromisoformat(ts_raw) if isinstance(ts_raw, str) else None
            except ValueError:
                ts = None
            if ts is None:
                ts = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            # Only offer files where the owning process is no longer alive
            # *or* the file is clearly stale.
            file_age = now - stat.st_mtime
            if _is_pid_alive(pid) and file_age < stale_after_seconds:
                continue
            # Sanitise attacker-controllable session_id — only the safe
            # character set is carried forward; otherwise fall back to stem.
            raw_sid = data.get("session_id")
            if isinstance(raw_sid, str) and _SESSION_ID_RE.match(raw_sid):
                session_id = raw_sid
            else:
                session_id = path.stem
            orig_file = data.get("original_file")
            if not isinstance(orig_file, str):
                orig_file = None
            file_type = data.get("file_type")
            if not isinstance(file_type, str):
                file_type = None
            results.append(
                RecoverableSession(
                    path=path,
                    session_id=session_id,
                    timestamp=ts,
                    pid=pid,
                    original_file=orig_file,
                    file_type=file_type,
                    data=data,
                )
            )
        return results

    def discard_session_file(self, session: RecoverableSession) -> None:
        """Delete a recovered session file (user declined or recovery done)."""
        try:
            session.path.unlink(missing_ok=True)
        except OSError as exc:
            _LOG.warning("Failed to delete %s: %s", session.path, exc)

    # ------------------------------------------------------------ internals
    @staticmethod
    def _new_session_id() -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{stamp}-{os.getpid()}"

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=self._periodic)
            except queue.Empty:
                item = "periodic"
            if item is _SHUTDOWN_SENTINEL:
                return
            # If the item carries a pre-built snapshot, use the newest one
            # seen during the debounce window.
            latest_snapshot: Optional[Dict[str, Any]] = None
            if isinstance(item, tuple) and len(item) == 2 and item[0] == "snapshot":
                latest_snapshot = item[1]
            # Debounce: coalesce rapid events.
            deadline = time.monotonic() + self._debounce
            while time.monotonic() < deadline:
                try:
                    more = self._queue.get(timeout=max(0.0, deadline - time.monotonic()))
                except queue.Empty:
                    break
                if more is _SHUTDOWN_SENTINEL:
                    return
                if isinstance(more, tuple) and len(more) == 2 and more[0] == "snapshot":
                    latest_snapshot = more[1]
            try:
                self._write_once(blocking=False, preset_snapshot=latest_snapshot)
            except Exception as exc:  # noqa: BLE001
                _LOG.warning("Autosave write failed: %s", exc)

    def _write_once(
        self,
        *,
        blocking: bool,
        preset_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            snapshot: Optional[Dict[str, Any]]
            if preset_snapshot is not None:
                snapshot = preset_snapshot
            else:
                try:
                    snapshot = self._snapshot_fn()
                except Exception as exc:  # noqa: BLE001
                    _LOG.warning("Snapshot callback raised: %s", exc)
                    return
            if snapshot is None:
                # No work in progress — nothing to autosave.
                return
            payload = self._build_payload(snapshot)
            self._atomic_write(self.autosave_path(), payload)
            self._rotate_ring(self.autosave_path(), payload)
            self._last_write_ts = time.time()

    def _build_payload(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "version": AUTOSAVE_SCHEMA_VERSION,
            "session_id": self._session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pid": self._pid,
        }
        payload.update(snapshot)
        return payload

    @staticmethod
    def _atomic_write(target: Path, payload: Dict[str, Any]) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, target)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _rotate_ring(self, target: Path, payload: Dict[str, Any]) -> None:
        if self._ring_size <= 1:
            return
        stem = target.name  # e.g. "<session>.autosave.json"
        ring_tag = f"{int(time.time() * 1000) % 1_000_000_000}"
        ring_path = target.parent / f"{stem}.ring-{ring_tag}.json"
        try:
            # Use the same atomic write path as the primary file so a crash
            # mid-rotation can never leave a torn ring entry behind.
            self._atomic_write(ring_path, payload)
        except OSError as exc:
            _LOG.debug("Ring buffer write skipped: %s", exc)
            return
        # Prune oldest if we exceed ring_size.
        pattern = f"{stem}.ring-*.json"
        ring_files = sorted(
            target.parent.glob(pattern), key=lambda p: p.stat().st_mtime
        )
        while len(ring_files) > self._ring_size:
            oldest = ring_files.pop(0)
            try:
                oldest.unlink()
            except OSError:
                pass

    def _delete_current_file(self) -> None:
        path = self.autosave_path()
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            _LOG.warning("Failed to delete autosave file %s: %s", path, exc)
        # Also clean up this session's ring buffer files.
        for ring in path.parent.glob(path.name + ".ring-*.json"):
            try:
                ring.unlink()
            except OSError:
                pass
