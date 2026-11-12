import wx
from ai_translator import AITranslator
from mutt.constants import UpdateEvent, ResultEvent

def run_translation_thread(parent_frame, active_provider, settings, context):
    def p_cb(p, t): wx.PostEvent(parent_frame, UpdateEvent(value=p, total=t))
    try:
        # Termbase hints: approved translations for terms that actually occur
        # in this run. Advisory only - _build_user_prompt tells the model it
        # may override them when the context differs.
        glossary = {}
        try:
            tm = getattr(parent_frame, "translation_memory", None)
            if tm is not None and parent_frame.config.get("use_termbase", True):
                glossary = tm.find_matches(
                    [e.get("msgid", "") for e in (parent_frame.po_entries or [])],
                    parent_frame.source_language,
                    parent_frame.target_language,
                )
        except Exception:
            parent_frame.logger.exception("Termbase lookup failed; continuing without it")

        translator = AITranslator(
            active_provider,
            settings.get("api_key"),
            settings.get("api_model"),
            glossary=glossary,
            batch_size=parent_frame.config.get("batch_size", 200),
            temperature=parent_frame.config.get("temperature", 0.1),
            max_batch_tokens=parent_frame.config.get("max_batch_tokens", 16000),
            extra_settings=settings
        )

        # Resolve per-entry positions in ``all_po_entries`` so the translator
        # can compute a correct context window per sub-batch. We match by
        # object identity first (robust to duplicate msgids in gettext files
        # where the dicts are shared references) and fall back to msgid.
        all_entries = parent_frame.all_po_entries or []
        po_entries = parent_frame.po_entries or []
        po_entries_positions = []
        if all_entries and po_entries:
            id_to_pos = {id(e): i for i, e in enumerate(all_entries)}
            # Track already-used positions to disambiguate duplicate msgids
            used_positions: set[int] = set()
            msgid_candidates: dict[str, list[int]] = {}
            for i, e in enumerate(all_entries):
                msgid_candidates.setdefault(e.get('msgid', ''), []).append(i)
            for entry in po_entries:
                pos = id_to_pos.get(id(entry))
                if pos is None:
                    for cand in msgid_candidates.get(entry.get('msgid', ''), []):
                        if cand not in used_positions:
                            pos = cand
                            break
                if pos is None:
                    # Sentinel: unresolved. We still append so the parallel
                    # index structure holds, and the translator will disable
                    # context if lengths mismatch.
                    pos = -1
                used_positions.add(pos)
                po_entries_positions.append(pos)

        enable_ctx = parent_frame.config.get("enable_surrounding_context", True)
        prev_size = parent_frame.config.get("context_previous_size", 2) if enable_ctx else 0
        next_size = parent_frame.config.get("context_next_size", 2) if enable_ctx else 0

        cancel_event = getattr(parent_frame, "cancel_event", None)
        cancel_check = cancel_event.is_set if cancel_event is not None else None

        trans_data, usage = translator.translate_entries(
            po_entries,
            parent_frame.source_language, # Use instance variable
            parent_frame.target_language, # Use instance variable
            context,
            p_cb,
            all_po_entries=all_entries,
            po_entries_positions=po_entries_positions,
            context_previous_size=prev_size,
            context_next_size=next_size,
            cancel_check=cancel_check,
        )
        wx.PostEvent(parent_frame, ResultEvent(source="translation", result=trans_data, usage=usage, error=None))
    except Exception as e:
        wx.PostEvent(parent_frame, ResultEvent(source="translation", error=e))
