"""User-level API key protection via the OS keyring.

API keys are stored in the operating-system credential vault
(Windows Credential Manager / macOS Keychain / Linux Secret Service)
and only a placeholder ``"keyring:<provider>"`` is written to ``config.json``.

Runtime usage:
    * ``hydrate_config(cfg)`` — call after loading the JSON to replace
      placeholders with the real keys (in place).
    * ``dehydrate_config_for_disk(cfg)`` — call before writing the JSON
      back; returns a deep copy with plaintext keys moved to the keyring
      and replaced by placeholders.

Plaintext keys already present in an old ``config.json`` are migrated
transparently the next time the file is saved.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

try:
    import keyring  # type: ignore

    _KEYRING_AVAILABLE = True
except Exception:  # pragma: no cover - import guard
    keyring = None  # type: ignore
    _KEYRING_AVAILABLE = False

logger = logging.getLogger("MUTT")

SERVICE_NAME = "MUTT"
PLACEHOLDER_PREFIX = "keyring:"


def is_available() -> bool:
    """Return True when the ``keyring`` backend is importable."""
    return _KEYRING_AVAILABLE


def _placeholder(provider: str) -> str:
    return f"{PLACEHOLDER_PREFIX}{provider}"


def _is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(PLACEHOLDER_PREFIX)


def store_key(provider: str, key: str) -> bool:
    """Persist ``key`` for ``provider`` in the OS keyring. Returns True on success."""
    if not _KEYRING_AVAILABLE or not key:
        return False
    try:
        keyring.set_password(SERVICE_NAME, provider, key)
        return True
    except Exception as exc:
        logger.warning("Failed to store key for '%s' in keyring: %s", provider, exc)
        return False


def fetch_key(provider: str) -> str:
    """Retrieve the key for ``provider`` from the OS keyring (empty string if absent)."""
    if not _KEYRING_AVAILABLE:
        return ""
    try:
        return keyring.get_password(SERVICE_NAME, provider) or ""
    except Exception as exc:
        logger.warning("Failed to fetch key for '%s' from keyring: %s", provider, exc)
        return ""


def delete_key(provider: str) -> None:
    """Best-effort removal of ``provider``'s key from the OS keyring."""
    if not _KEYRING_AVAILABLE:
        return
    try:
        keyring.delete_password(SERVICE_NAME, provider)
    except Exception:
        pass


def hydrate_config(config: dict) -> dict:
    """Replace ``keyring:`` placeholders inside ``config['providers']`` with the real keys.

    Mutates ``config`` in place and also returns it for convenience.
    """
    providers = config.get("providers") or {}
    for name, settings in providers.items():
        if not isinstance(settings, dict):
            continue
        val = settings.get("api_key", "")
        if _is_placeholder(val):
            settings["api_key"] = fetch_key(name)
    return config


def dehydrate_config_for_disk(config: dict) -> dict:
    """Return a deep copy of ``config`` safe to write to disk.

    For every provider with a non-empty plaintext ``api_key``:
      * the key is stored in the OS keyring, and
      * the value in the returned copy is replaced with ``"keyring:<provider>"``.

    Empty keys and existing placeholders are left untouched. If the
    keyring backend is unavailable, the plaintext key is preserved so
    nothing is lost.
    """
    snapshot = copy.deepcopy(config)
    providers = snapshot.get("providers") or {}
    for name, settings in providers.items():
        if not isinstance(settings, dict):
            continue
        val = settings.get("api_key", "")
        if not val or _is_placeholder(val):
            continue
        if store_key(name, val):
            settings["api_key"] = _placeholder(name)
    return snapshot
