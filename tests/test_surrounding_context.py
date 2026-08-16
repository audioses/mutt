"""Tests for the surrounding-context feature.

Covers the rebuilt contract: ``translate_entries`` now receives
``all_po_entries`` + ``po_entries_positions`` and builds a per-sub-batch
``{"previous": [...], "next": [...]}`` window, rather than receiving a
single flat list whose role is guessed from ``msgstr`` presence.

Scenarios:
  * fresh file (no msgstr yet) — previous window shows "(not yet translated)"
  * fully translated file — previous window shows ``Source -> Target``
  * selective filter (non-contiguous po_entries) — anchors correctly
  * duplicate msgids — anchors by object identity
  * multi-batch run — each batch gets its own window
  * ``_build_user_prompt`` renders both dict and legacy list forms
"""
from __future__ import annotations

from ai_translator import AITranslator


# ---------- _build_user_prompt rendering ---------------------------------

def _make_translator():
    return AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini")


def test_prompt_renders_dict_form_with_previous_and_next():
    t = _make_translator()
    ctx = {
        "previous": [
            {"msgid": "Hello", "msgstr": "Merhaba"},
            {"msgid": "World", "msgstr": ""},  # not translated yet — should still be ordered in PREVIOUS
        ],
        "next": [
            {"msgid": "Goodbye", "msgstr": ""},
        ],
    }
    prompt = t._build_user_prompt(["Foo"], "en", "tr", None, surrounding_context=ctx)
    assert "preceding" in prompt
    assert "following" in prompt
    # Translated preceding entry: shown as source -> target
    assert '"Hello" -> Target: "Merhaba"' in prompt
    # Untranslated preceding entry: explicit marker, NOT shuffled into "following"
    assert '"World" (not yet translated)' in prompt
    # "following" section carries only source.
    assert 'Source: "Goodbye"' in prompt
    assert 'Goodbye" -> Target' not in prompt


def test_prompt_preserves_order_within_previous_and_next():
    t = _make_translator()
    ctx = {
        "previous": [{"msgid": f"p{i}", "msgstr": f"P{i}"} for i in range(3)],
        "next":     [{"msgid": f"n{i}", "msgstr": ""} for i in range(3)],
    }
    prompt = t._build_user_prompt(["x"], "en", "tr", None, surrounding_context=ctx)
    assert prompt.index("p0") < prompt.index("p1") < prompt.index("p2")
    assert prompt.index("n0") < prompt.index("n1") < prompt.index("n2")
    assert prompt.index("p2") < prompt.index("n0"), "previous section must come before next"


def test_prompt_legacy_list_form_still_supported():
    """Any external caller passing the old flat list must still produce
    a sane prompt — use msgstr presence as a heuristic fallback."""
    t = _make_translator()
    flat = [
        {"msgid": "A", "msgstr": "a"},   # "translated" → previous bucket
        {"msgid": "B", "msgstr": ""},    # "not yet"    → next bucket
    ]
    prompt = t._build_user_prompt(["x"], "en", "tr", None, surrounding_context=flat)
    assert '"A" -> Target: "a"' in prompt
    assert 'Source: "B"' in prompt


def test_prompt_without_context_omits_context_sections():
    t = _make_translator()
    prompt = t._build_user_prompt(["x"], "en", "tr", None, surrounding_context=None)
    assert "preceding the ones" not in prompt
    assert "entries immediately following" not in prompt

    prompt2 = t._build_user_prompt(["x"], "en", "tr", None, surrounding_context={"previous": [], "next": []})
    assert "preceding the ones" not in prompt2
    assert "entries immediately following" not in prompt2


# ---------- translate_entries window computation -------------------------

def _capture_process_batch(translator, monkeypatch):
    """Replace ``_process_batch`` with a recorder that returns empty strings
    of the right length and captures the context window passed to it."""
    captured: list[dict] = []

    def _fake(batch_texts, source, target, context, surrounding_context, batch_entries=None):
        captured.append({
            "texts": list(batch_texts),
            "window": surrounding_context,
            "entries": list(batch_entries or []),
        })
        return [""] * len(batch_texts), {"prompt_tokens": 0, "completion_tokens": 0}

    monkeypatch.setattr(translator, "_process_batch", _fake)
    # Pretend the client is ready so translate_entries doesn't try to hit the network.
    translator._client_initialized = True
    # Skip the per-batch 1s cooldown during tests.
    monkeypatch.setattr("ai_translator.time.sleep", lambda *_a, **_k: None)
    return captured


def test_window_for_fresh_file_shows_untranslated_previous(monkeypatch):
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini", batch_size=2)
    captured = _capture_process_batch(t, monkeypatch)

    all_entries = [
        {"msgid": "pre-1", "msgstr": ""},
        {"msgid": "pre-2", "msgstr": ""},
        {"msgid": "t-1",   "msgstr": ""},
        {"msgid": "t-2",   "msgstr": ""},
        {"msgid": "nxt-1", "msgstr": ""},
        {"msgid": "nxt-2", "msgstr": ""},
    ]
    entries = all_entries[2:4]  # translating just t-1 and t-2
    positions = [2, 3]
    t.translate_entries(
        entries, "en", "tr",
        all_po_entries=all_entries,
        po_entries_positions=positions,
        context_previous_size=2, context_next_size=2,
    )
    assert captured, "process_batch was not called"
    window = captured[0]["window"]
    assert [e["msgid"] for e in window["previous"]] == ["pre-1", "pre-2"]
    assert [e["msgid"] for e in window["next"]] == ["nxt-1", "nxt-2"]


def test_window_for_fully_translated_file_carries_targets(monkeypatch):
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini", batch_size=1)
    captured = _capture_process_batch(t, monkeypatch)

    all_entries = [
        {"msgid": "p", "msgstr": "P-tr"},
        {"msgid": "t", "msgstr": "t-old-tr"},  # being re-translated
        {"msgid": "n", "msgstr": "N-tr"},
    ]
    entries = [all_entries[1]]
    positions = [1]
    t.translate_entries(
        entries, "en", "tr",
        all_po_entries=all_entries,
        po_entries_positions=positions,
        context_previous_size=1, context_next_size=1,
    )
    window = captured[0]["window"]
    assert window["previous"][0]["msgstr"] == "P-tr"
    assert window["next"][0]["msgstr"] == "N-tr"


def test_window_respects_non_contiguous_po_entries(monkeypatch):
    """User filtered to only untranslated — po_entries is a SUBSET with
    gaps. The window must still anchor correctly, not include the other
    po_entries as context."""
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini", batch_size=1)
    captured = _capture_process_batch(t, monkeypatch)

    all_entries = [
        {"msgid": "A", "msgstr": ""},        # 0 — untranslated, IS in po_entries
        {"msgid": "B", "msgstr": "B-done"},  # 1 — translated, NOT in po_entries
        {"msgid": "C", "msgstr": ""},        # 2 — untranslated, IS in po_entries
        {"msgid": "D", "msgstr": "D-done"},  # 3 — translated, NOT in po_entries
    ]
    entries = [all_entries[0], all_entries[2]]
    positions = [0, 2]

    t.translate_entries(
        entries, "en", "tr",
        all_po_entries=all_entries,
        po_entries_positions=positions,
        context_previous_size=2, context_next_size=2,
    )
    # batch_size=1 → two sub-batches
    assert len(captured) == 2
    # Batch 1 translates A at position 0 → previous empty, next shows B
    w1 = captured[0]["window"]
    assert w1["previous"] == []
    assert [e["msgid"] for e in w1["next"]] == ["B", "C"]
    # Batch 2 translates C at position 2 → previous shows A, B; next shows D
    w2 = captured[1]["window"]
    assert [e["msgid"] for e in w2["previous"]] == ["A", "B"]
    assert [e["msgid"] for e in w2["next"]] == ["D"]


def test_duplicate_msgids_anchor_by_identity(monkeypatch):
    """Gettext supports multiple entries with the same msgid (disambiguated
    by msgctxt). The resolver must not collapse them onto the first match."""
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini", batch_size=1)
    captured = _capture_process_batch(t, monkeypatch)

    dup_a = {"msgid": "dup", "msgstr": ""}
    dup_b = {"msgid": "dup", "msgstr": ""}
    all_entries = [
        {"msgid": "one", "msgstr": "1"},
        dup_a,                          # index 1
        {"msgid": "mid", "msgstr": "m"},
        dup_b,                          # index 3
        {"msgid": "end", "msgstr": "e"},
    ]
    entries = [dup_b]  # we're translating the SECOND duplicate only
    positions = [3]    # caller resolved by identity

    t.translate_entries(
        entries, "en", "tr",
        all_po_entries=all_entries,
        po_entries_positions=positions,
        context_previous_size=1, context_next_size=1,
    )
    w = captured[0]["window"]
    # previous should be ``mid`` (index 2), not ``one`` (index 0)
    assert [e["msgid"] for e in w["previous"]] == ["mid"]
    assert [e["msgid"] for e in w["next"]] == ["end"]


def test_multi_batch_each_gets_its_own_window(monkeypatch):
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini", batch_size=2)
    captured = _capture_process_batch(t, monkeypatch)

    all_entries = [{"msgid": f"e{i}", "msgstr": ""} for i in range(10)]
    entries = all_entries[:]  # translating all
    positions = list(range(10))

    t.translate_entries(
        entries, "en", "tr",
        all_po_entries=all_entries,
        po_entries_positions=positions,
        context_previous_size=1, context_next_size=1,
    )
    assert len(captured) == 5  # 10 entries / batch_size 2
    # First batch: positions [0,1] → prev=[], next=[e2]
    assert captured[0]["window"]["previous"] == []
    assert [e["msgid"] for e in captured[0]["window"]["next"]] == ["e2"]
    # Middle batch: positions [4,5] → prev=[e3], next=[e6]
    assert [e["msgid"] for e in captured[2]["window"]["previous"]] == ["e3"]
    assert [e["msgid"] for e in captured[2]["window"]["next"]] == ["e6"]
    # Last batch: positions [8,9] → prev=[e7], next=[]
    assert [e["msgid"] for e in captured[4]["window"]["previous"]] == ["e7"]
    assert captured[4]["window"]["next"] == []


def test_context_disabled_produces_no_window(monkeypatch):
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini", batch_size=2)
    captured = _capture_process_batch(t, monkeypatch)

    all_entries = [{"msgid": f"e{i}", "msgstr": ""} for i in range(4)]
    t.translate_entries(
        all_entries[:2], "en", "tr",
        all_po_entries=all_entries,
        po_entries_positions=[0, 1],
        context_previous_size=0, context_next_size=0,
    )
    assert captured[0]["window"] is None


def test_no_position_data_disables_context(monkeypatch):
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini", batch_size=2)
    captured = _capture_process_batch(t, monkeypatch)
    t.translate_entries(
        [{"msgid": "x", "msgstr": ""}], "en", "tr",
        context_previous_size=2, context_next_size=2,
    )
    assert captured[0]["window"] is None


def test_obsolete_entries_are_skipped_for_position_mapping(monkeypatch):
    """Obsolete entries aren't translated, so they should not consume a
    position slot — the translator must align the non-obsolete items
    with their positions in all_po_entries."""
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini", batch_size=1)
    captured = _capture_process_batch(t, monkeypatch)

    all_entries = [
        {"msgid": "a", "msgstr": ""},
        {"msgid": "obs", "msgstr": "", "obsolete": True},
        {"msgid": "b", "msgstr": ""},
    ]
    entries = all_entries[:]
    positions = [0, 1, 2]
    t.translate_entries(
        entries, "en", "tr",
        all_po_entries=all_entries,
        po_entries_positions=positions,
        context_previous_size=1, context_next_size=1,
    )
    # Two non-obsolete entries → two batches (batch_size=1)
    assert len(captured) == 2
    # First sub-batch translates "a" at position 0
    assert captured[0]["texts"] == ["a"]
    assert captured[0]["window"]["previous"] == []
    # "next" should include the obsolete sibling and "b" (N=1 means window of 1 after position 0)
    assert [e["msgid"] for e in captured[0]["window"]["next"]] == ["obs"]
    # Second sub-batch translates "b" at position 2; previous should be ["obs"]
    assert captured[1]["texts"] == ["b"]
    assert [e["msgid"] for e in captured[1]["window"]["previous"]] == ["obs"]
