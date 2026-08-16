"""Tests for cooperative cancellation of the translation loop.

The translator polls ``cancel_check`` between batches (LLM) and between entries
(Argos). On cancel it stops and returns whatever was already translated, with
``usage['cancelled'] == True``, so the user never loses partial work.
"""
from ai_translator import AITranslator


def _make_llm_translator(monkeypatch, batch_size=2):
    t = AITranslator("OpenAI GPT", "key", "gpt-4", batch_size=batch_size)
    monkeypatch.setattr(t, "_initialize_client", lambda: None)
    monkeypatch.setattr("ai_translator.time.sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_process(sub_msgids, src, tgt, context, window, batch_entries=None):
        calls["n"] += 1
        return [f"T:{m}" for m in sub_msgids], {"prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(t, "_process_batch", fake_process)
    return t, calls


def test_llm_cancel_keeps_partial(monkeypatch):
    t, calls = _make_llm_translator(monkeypatch, batch_size=2)
    entries = [{"msgid": f"s{i}", "msgstr": ""} for i in range(6)]

    # Cancel as soon as the first batch has been processed.
    def cancel_check():
        return calls["n"] >= 1

    result, usage = t.translate_entries(entries, "en", "es", cancel_check=cancel_check)

    assert usage["cancelled"] is True
    # batch_size 2 → first batch covers entries 0,1; cancel fires before batch 2.
    assert result[0]["msgstr"] == "T:s0"
    assert result[1]["msgstr"] == "T:s1"
    assert result[2]["msgstr"] == ""  # never reached
    translated = [e for e in result if e["msgstr"]]
    assert len(translated) == 2


def test_llm_completes_without_cancel(monkeypatch):
    t, _ = _make_llm_translator(monkeypatch, batch_size=2)
    entries = [{"msgid": f"s{i}", "msgstr": ""} for i in range(4)]

    result, usage = t.translate_entries(entries, "en", "es", cancel_check=lambda: False)

    assert usage["cancelled"] is False
    assert all(e["msgstr"] == f"T:s{i}" for i, e in enumerate(result))


def test_no_cancel_check_is_accepted(monkeypatch):
    t, _ = _make_llm_translator(monkeypatch, batch_size=5)
    entries = [{"msgid": "only", "msgstr": ""}]
    result, usage = t.translate_entries(entries, "en", "es")
    assert usage["cancelled"] is False
    assert result[0]["msgstr"] == "T:only"
