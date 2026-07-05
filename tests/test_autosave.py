"""Tests for the autosave / crash-recovery manager."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from mutt.logic.autosave import (
    AUTOSAVE_SCHEMA_VERSION,
    AutosaveManager,
    RecoverableSession,
    _is_pid_alive,
)


def _make_manager(
    tmp_path: Path,
    snapshot: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> AutosaveManager:
    payload = dict(snapshot) if snapshot is not None else {"hello": "world"}

    def snap() -> Optional[Dict[str, Any]]:
        return payload

    return AutosaveManager(
        snapshot_fn=snap,
        autosave_dir=tmp_path,
        debounce_seconds=0.01,
        periodic_seconds=5.0,
        ring_size=3,
        **kwargs,
    )


def _wait_for_file(path: Path, timeout: float = 3.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists() and path.stat().st_size > 0:
            return True
        time.sleep(0.02)
    return False


def test_atomic_write_creates_file(tmp_path: Path):
    mgr = _make_manager(tmp_path, {"current_index": 7})
    mgr.start()
    try:
        mgr.request_save()
        assert _wait_for_file(mgr.autosave_path())
        with mgr.autosave_path().open(encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["version"] == AUTOSAVE_SCHEMA_VERSION
        assert data["current_index"] == 7
        assert data["pid"] == os.getpid()
        assert "timestamp" in data
    finally:
        mgr.stop(flush=False)


def test_snapshot_none_skips_write(tmp_path: Path):
    def snap() -> Optional[Dict[str, Any]]:
        return None

    mgr = AutosaveManager(
        snapshot_fn=snap, autosave_dir=tmp_path, debounce_seconds=0.01
    )
    mgr.start()
    try:
        mgr.request_save()
        time.sleep(0.2)
        assert not mgr.autosave_path().exists()
    finally:
        mgr.stop(flush=False)


def test_stop_with_delete_removes_file(tmp_path: Path):
    mgr = _make_manager(tmp_path)
    mgr.start()
    try:
        mgr.request_save()
        assert _wait_for_file(mgr.autosave_path())
    finally:
        mgr.stop(flush=False, delete=True)
    assert not mgr.autosave_path().exists()


def test_recovery_finds_files_from_dead_pids(tmp_path: Path):
    # Write a fake autosave file from a PID that is almost certainly dead.
    fake_path = tmp_path / "20000101-000000-99999.autosave.json"
    payload = {
        "version": AUTOSAVE_SCHEMA_VERSION,
        "session_id": "20000101-000000-99999",
        "timestamp": "2000-01-01T00:00:00+00:00",
        "pid": 99_999_999,  # definitely not alive
        "original_file": "C:/foo/bar.docx",
        "file_type": "DOCX",
        "review_entries": [{"msgid": "hi", "msgstr": "hola"}],
    }
    fake_path.write_text(json.dumps(payload), encoding="utf-8")

    mgr = _make_manager(tmp_path)
    sessions = mgr.find_recoverable_sessions()
    assert len(sessions) == 1
    assert sessions[0].original_file == "C:/foo/bar.docx"
    assert sessions[0].file_type == "DOCX"


def test_recovery_skips_files_from_our_own_session(tmp_path: Path):
    mgr = _make_manager(tmp_path)
    mgr.start()
    try:
        mgr.request_save()
        assert _wait_for_file(mgr.autosave_path())
    finally:
        mgr.stop(flush=False)

    # The file still exists — make sure the same manager doesn't offer it back.
    assert mgr.autosave_path().exists()
    sessions = mgr.find_recoverable_sessions()
    assert all(
        not s.path.name.startswith(mgr.autosave_path().name.split(".")[0])
        for s in sessions
    )


def test_recovery_skips_files_from_live_pid_when_fresh(tmp_path: Path):
    live_path = tmp_path / "live.autosave.json"
    payload = {
        "version": AUTOSAVE_SCHEMA_VERSION,
        "session_id": "live",
        "timestamp": "2026-04-15T00:00:00+00:00",
        "pid": os.getpid(),
        "original_file": "foo",
    }
    live_path.write_text(json.dumps(payload), encoding="utf-8")

    mgr = _make_manager(tmp_path)
    sessions = mgr.find_recoverable_sessions(stale_after_seconds=3600)
    # Our own PID is alive; file is fresh → should not be offered.
    assert all(s.path != live_path for s in sessions)


def test_is_pid_alive_current_process_true():
    assert _is_pid_alive(os.getpid()) is True


def test_is_pid_alive_zero_false():
    assert _is_pid_alive(0) is False


def test_discard_session_file_removes_it(tmp_path: Path):
    victim = tmp_path / "victim.autosave.json"
    victim.write_text("{}", encoding="utf-8")
    mgr = _make_manager(tmp_path)
    session = RecoverableSession(
        path=victim,
        session_id="victim",
        timestamp=None,  # type: ignore[arg-type]
        pid=0,
        original_file=None,
        file_type=None,
    )
    mgr.discard_session_file(session)
    assert not victim.exists()


def test_concurrent_request_save_from_many_threads(tmp_path: Path):
    counter = {"n": 0}
    lock = threading.Lock()

    def snap() -> Dict[str, Any]:
        with lock:
            counter["n"] += 1
            return {"n": counter["n"]}

    mgr = AutosaveManager(
        snapshot_fn=snap,
        autosave_dir=tmp_path,
        debounce_seconds=0.05,
        periodic_seconds=10.0,
    )
    mgr.start()
    try:
        threads = [
            threading.Thread(target=mgr.request_save) for _ in range(25)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert _wait_for_file(mgr.autosave_path())
        # The writer should have coalesced many requests into a small number
        # of writes, but at least one snapshot must have happened.
        assert counter["n"] >= 1
    finally:
        mgr.stop(flush=False)


def test_ring_buffer_retains_history(tmp_path: Path):
    payloads = [{"i": 0}]

    def snap() -> Dict[str, Any]:
        return payloads[0]

    mgr = AutosaveManager(
        snapshot_fn=snap,
        autosave_dir=tmp_path,
        debounce_seconds=0.0,
        periodic_seconds=10.0,
        ring_size=3,
    )
    mgr.start()
    try:
        for i in range(6):
            payloads[0] = {"i": i}
            mgr.request_save()
            time.sleep(0.1)
        # Wait for writes to flush.
        time.sleep(0.3)
    finally:
        mgr.stop(flush=True)

    ring_files = list(tmp_path.glob("*.ring-*.json"))
    # Ring is bounded by ring_size (3).
    assert len(ring_files) <= 3
    assert len(ring_files) >= 1


def test_request_save_accepts_preset_snapshot(tmp_path: Path):
    """request_save(snapshot=...) must use the caller-supplied dict."""
    called = {"n": 0}

    def snap_that_should_not_be_called() -> Optional[Dict[str, Any]]:
        called["n"] += 1
        return {"from": "callback"}

    mgr = AutosaveManager(
        snapshot_fn=snap_that_should_not_be_called,
        autosave_dir=tmp_path,
        debounce_seconds=0.0,
        periodic_seconds=60.0,
    )
    mgr.start()
    try:
        mgr.request_save(snapshot={"from": "preset", "current_index": 42})
        assert _wait_for_file(mgr.autosave_path())
        with mgr.autosave_path().open(encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["from"] == "preset"
        assert data["current_index"] == 42
        assert called["n"] == 0
    finally:
        mgr.stop(flush=False)


def test_find_recoverable_skips_oversized_file(tmp_path: Path):
    from mutt.logic.autosave import _MAX_AUTOSAVE_BYTES

    big_path = tmp_path / "huge.autosave.json"
    # Write a bit over the limit with filler bytes (still valid-ish JSON at start).
    with big_path.open("wb") as fh:
        fh.write(b'{"pid": 1, "x": "')
        fh.write(b"A" * (_MAX_AUTOSAVE_BYTES + 10))
        fh.write(b'"}')

    mgr = _make_manager(tmp_path)
    sessions = mgr.find_recoverable_sessions()
    assert all(s.path != big_path for s in sessions)


def test_find_recoverable_sanitises_malicious_session_id(tmp_path: Path):
    evil_path = tmp_path / "evil.autosave.json"
    evil_path.write_text(
        json.dumps(
            {
                "version": AUTOSAVE_SCHEMA_VERSION,
                "session_id": "../../../etc/passwd",
                "pid": 99_999_999,
                "timestamp": "2000-01-01T00:00:00+00:00",
                "original_file": "C:/x/y.docx",
            }
        ),
        encoding="utf-8",
    )
    mgr = _make_manager(tmp_path)
    sessions = mgr.find_recoverable_sessions()
    assert len(sessions) == 1
    # session_id must NOT retain the traversal string — it falls back to
    # the stem of the path when the raw value fails validation.
    assert ".." not in sessions[0].session_id
    assert "/" not in sessions[0].session_id


def test_find_recoverable_rejects_non_dict_payload(tmp_path: Path):
    weird = tmp_path / "array.autosave.json"
    weird.write_text("[1, 2, 3]", encoding="utf-8")
    mgr = _make_manager(tmp_path)
    sessions = mgr.find_recoverable_sessions()
    assert all(s.path != weird for s in sessions)


def test_flush_on_stop(tmp_path: Path):
    data = {"latest": "value"}

    def snap() -> Dict[str, Any]:
        return data

    mgr = AutosaveManager(
        snapshot_fn=snap,
        autosave_dir=tmp_path,
        debounce_seconds=0.5,
        periodic_seconds=60.0,
    )
    mgr.start()
    data["latest"] = "changed"
    # Immediately stop with flush=True — the flush must write even though
    # the debounce window hasn't elapsed.
    mgr.stop(flush=True, delete=False)

    path = mgr.autosave_path()
    assert path.exists()
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["latest"] == "changed"
