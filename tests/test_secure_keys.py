"""Unit tests for mutt.secure_keys.

The OS keyring is replaced by an in-memory dict so tests run cross-platform
without touching the user's real credential vault.
"""
from __future__ import annotations

import pytest

from mutt import secure_keys


@pytest.fixture
def fake_keyring(monkeypatch):
    """Replace the keyring backend with an in-memory dict."""
    store: dict[tuple[str, str], str] = {}

    class _FakeKeyring:
        @staticmethod
        def set_password(service: str, name: str, password: str) -> None:
            store[(service, name)] = password

        @staticmethod
        def get_password(service: str, name: str):
            return store.get((service, name))

        @staticmethod
        def delete_password(service: str, name: str) -> None:
            store.pop((service, name), None)

    monkeypatch.setattr(secure_keys, "keyring", _FakeKeyring)
    monkeypatch.setattr(secure_keys, "_KEYRING_AVAILABLE", True)
    return store


# ---------- placeholder helpers ------------------------------------------

def test_placeholder_format():
    assert secure_keys._placeholder("OpenAI GPT") == "keyring:OpenAI GPT"


def test_is_placeholder_detection():
    assert secure_keys._is_placeholder("keyring:foo")
    assert not secure_keys._is_placeholder("sk-real-key")
    assert not secure_keys._is_placeholder("")
    assert not secure_keys._is_placeholder(None)
    assert not secure_keys._is_placeholder(42)


# ---------- store / fetch / delete ---------------------------------------

def test_store_and_fetch_roundtrip(fake_keyring):
    assert secure_keys.store_key("OpenAI GPT", "sk-secret") is True
    assert secure_keys.fetch_key("OpenAI GPT") == "sk-secret"


def test_store_empty_key_is_noop(fake_keyring):
    assert secure_keys.store_key("OpenAI GPT", "") is False
    assert secure_keys.fetch_key("OpenAI GPT") == ""


def test_fetch_missing_returns_empty_string(fake_keyring):
    assert secure_keys.fetch_key("Nope") == ""


def test_delete_removes_key(fake_keyring):
    secure_keys.store_key("OpenRouter", "sk-or")
    secure_keys.delete_key("OpenRouter")
    assert secure_keys.fetch_key("OpenRouter") == ""


def test_delete_missing_does_not_raise(fake_keyring):
    secure_keys.delete_key("Never-Stored")  # must not raise


def test_store_swallows_backend_errors(monkeypatch):
    monkeypatch.setattr(secure_keys, "_KEYRING_AVAILABLE", True)

    class Boom:
        @staticmethod
        def set_password(*_a, **_kw):
            raise RuntimeError("backend down")

    monkeypatch.setattr(secure_keys, "keyring", Boom)
    assert secure_keys.store_key("X", "k") is False


def test_fetch_swallows_backend_errors(monkeypatch):
    monkeypatch.setattr(secure_keys, "_KEYRING_AVAILABLE", True)

    class Boom:
        @staticmethod
        def get_password(*_a, **_kw):
            raise RuntimeError("backend down")

    monkeypatch.setattr(secure_keys, "keyring", Boom)
    assert secure_keys.fetch_key("X") == ""


def test_no_backend_means_noop(monkeypatch):
    monkeypatch.setattr(secure_keys, "_KEYRING_AVAILABLE", False)
    assert secure_keys.store_key("X", "k") is False
    assert secure_keys.fetch_key("X") == ""
    secure_keys.delete_key("X")  # must not raise


# ---------- hydrate_config ------------------------------------------------

def test_hydrate_replaces_placeholders_with_real_keys(fake_keyring):
    secure_keys.store_key("OpenAI GPT", "sk-real")
    cfg = {"providers": {"OpenAI GPT": {"api_key": "keyring:OpenAI GPT", "api_model": "gpt-4o"}}}
    out = secure_keys.hydrate_config(cfg)
    assert out["providers"]["OpenAI GPT"]["api_key"] == "sk-real"


def test_hydrate_leaves_plaintext_keys_alone(fake_keyring):
    cfg = {"providers": {"OpenAI GPT": {"api_key": "sk-plain", "api_model": "x"}}}
    out = secure_keys.hydrate_config(cfg)
    assert out["providers"]["OpenAI GPT"]["api_key"] == "sk-plain"


def test_hydrate_handles_missing_providers(fake_keyring):
    secure_keys.hydrate_config({})  # must not raise
    secure_keys.hydrate_config({"providers": None})


def test_hydrate_skips_non_dict_providers(fake_keyring):
    cfg = {"providers": {"OpenAI GPT": "broken"}}
    secure_keys.hydrate_config(cfg)  # must not raise


def test_hydrate_missing_key_resolves_to_empty_string(fake_keyring):
    """Placeholder for a provider that was never stored → empty string,
    matching the prior behaviour for an unset key."""
    cfg = {"providers": {"OpenAI GPT": {"api_key": "keyring:OpenAI GPT"}}}
    out = secure_keys.hydrate_config(cfg)
    assert out["providers"]["OpenAI GPT"]["api_key"] == ""


# ---------- dehydrate_config_for_disk ------------------------------------

def test_dehydrate_moves_plaintext_to_keyring(fake_keyring):
    cfg = {"providers": {"OpenAI GPT": {"api_key": "sk-plain", "api_model": "gpt-4o"}}}
    on_disk = secure_keys.dehydrate_config_for_disk(cfg)
    # Disk view: placeholder
    assert on_disk["providers"]["OpenAI GPT"]["api_key"] == "keyring:OpenAI GPT"
    # Keyring received the plaintext
    assert secure_keys.fetch_key("OpenAI GPT") == "sk-plain"
    # Original cfg unchanged (deep-copied)
    assert cfg["providers"]["OpenAI GPT"]["api_key"] == "sk-plain"


def test_dehydrate_leaves_existing_placeholders_alone(fake_keyring):
    cfg = {"providers": {"OpenAI GPT": {"api_key": "keyring:OpenAI GPT"}}}
    out = secure_keys.dehydrate_config_for_disk(cfg)
    assert out["providers"]["OpenAI GPT"]["api_key"] == "keyring:OpenAI GPT"


def test_dehydrate_leaves_empty_keys_alone(fake_keyring):
    cfg = {"providers": {"HuggingFace": {"api_key": "", "api_model": "x", "device": "cpu"}}}
    out = secure_keys.dehydrate_config_for_disk(cfg)
    assert out["providers"]["HuggingFace"]["api_key"] == ""


def test_dehydrate_keeps_plaintext_when_keyring_unavailable(monkeypatch):
    monkeypatch.setattr(secure_keys, "_KEYRING_AVAILABLE", False)
    cfg = {"providers": {"OpenAI GPT": {"api_key": "sk-plain"}}}
    out = secure_keys.dehydrate_config_for_disk(cfg)
    # Without a backend we MUST NOT lose the user's key.
    assert out["providers"]["OpenAI GPT"]["api_key"] == "sk-plain"


def test_dehydrate_preserves_other_settings(fake_keyring):
    cfg = {
        "providers": {
            "Custom (OpenAI-Compatible)": {
                "api_key": "sk-c",
                "api_model": "llama-3-8b",
                "base_url": "http://localhost:8080/v1",
            }
        },
        "last_provider": "Custom (OpenAI-Compatible)",
        "batch_size": 50,
    }
    out = secure_keys.dehydrate_config_for_disk(cfg)
    p = out["providers"]["Custom (OpenAI-Compatible)"]
    assert p["api_model"] == "llama-3-8b"
    assert p["base_url"] == "http://localhost:8080/v1"
    assert out["last_provider"] == "Custom (OpenAI-Compatible)"
    assert out["batch_size"] == 50


# ---------- end-to-end roundtrip -----------------------------------------

def test_dehydrate_then_hydrate_recovers_original_key(fake_keyring):
    cfg = {"providers": {"OpenAI GPT": {"api_key": "sk-roundtrip", "api_model": "x"}}}
    on_disk = secure_keys.dehydrate_config_for_disk(cfg)
    # Simulate writing/reading by passing the disk snapshot to hydrate.
    rehydrated = secure_keys.hydrate_config(on_disk)
    assert rehydrated["providers"]["OpenAI GPT"]["api_key"] == "sk-roundtrip"
