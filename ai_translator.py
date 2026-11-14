# ai_translator.py

import json
import logging
import time
import re
from local_model_manager import LocalModelManager
from mutt.logic.plurals import plural_forms, set_target_for_form
from mutt.logic.notes import guidance_notes

# Share the MainFrame's logger so [OpenAI] traces land in mutt_debug.log.
_logger = logging.getLogger("MUTT")

# Separate rotating log file dedicated to raw API responses. Kept out of the
# main debug log because bodies can be large. Rotates at 5 MB × 3 backups.
_response_logger = logging.getLogger("MUTT.responses")
_response_logger.propagate = False
if not _response_logger.handlers:  # pragma: no cover - one-time side effect
    try:
        from logging.handlers import RotatingFileHandler
        _rh = RotatingFileHandler(
            "openai_responses.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
            delay=True,
        )
        _rh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        _response_logger.addHandler(_rh)
        _response_logger.setLevel(logging.INFO)
    except Exception:
        pass


def _log(message: str) -> None:
    """Write to both stdout (visible in the console) and the shared log file."""
    print(message, flush=True)
    try:
        _logger.info(message)
    except Exception:
        pass


def _log_raw_response(tag: str, body: str, max_chars: int = 64_000) -> None:
    """Append the raw response body to ``openai_responses.log``.

    Truncates very large bodies so the log stays readable while still
    capturing the structure of the failure.
    """
    if not body:
        return
    truncated = body[:max_chars]
    if len(body) > max_chars:
        truncated = truncated + f"\n... [truncated {len(body) - max_chars} chars]"
    try:
        _response_logger.info("%s\n%s\n---", tag, truncated)
    except Exception:
        pass


def _extract_error_body(exc: Exception) -> str:
    """Best-effort extraction of the HTTP body that caused an SDK exception.

    Tries several attributes that the openai / httpx stack may expose
    before falling back to the string form of the exception itself.
    """
    for attr_chain in (
        ("response", "text"),
        ("body",),
        ("message",),
    ):
        obj = exc
        try:
            for attr in attr_chain:
                obj = getattr(obj, attr)
            if obj:
                return obj if isinstance(obj, str) else str(obj)
        except Exception:
            continue
    return str(exc)

# Models that require `max_completion_tokens` (and reject `max_tokens`)
# and that ignore non-default `temperature`.
# Patterns are matched case-insensitively against the model name.
_REASONING_MODEL_RE = re.compile(r"^(o1|o3|o4|gpt-5)", re.IGNORECASE)


def _is_reasoning_model(model_name: str) -> bool:
    """Return True for OpenAI reasoning-family models that require
    ``max_completion_tokens`` instead of ``max_tokens`` and only support
    the default ``temperature``."""
    return bool(model_name and _REASONING_MODEL_RE.match(model_name))


class AITranslator:
    def __init__(self, api_provider, api_key, model_name, batch_size=200, glossary=None, local_backend="Llama.cpp", temperature=0.1, max_batch_tokens=16000, extra_settings=None):
        self.api_provider = api_provider
        self.api_key = api_key
        self.glossary = glossary if glossary is not None else {}
        self.model_name = model_name
        # No ceiling: the configured size is honoured as written. A batch
        # too big for one reply comes back garbled or truncated, and
        # _process_batch halves it and retries rather than losing the job.
        self.batch_size = max(1, int(batch_size))
        self.temperature = temperature
        self._client = None  # Use a private variable for the client
        self._client_initialized = False # Flag to track if client has been initialized
        self.local_model_manager = LocalModelManager()
        self.local_backend = local_backend
        self.max_batch_tokens = int(max_batch_tokens)
        self.extra_settings = extra_settings or {}
        # Per-instance temperature preference for OpenAI-compatible endpoints.
        # Pre-seeded from the model name; refined at runtime if the server
        # returns a 400 unsupported_parameter error for temperature.
        # (max_tokens / max_completion_tokens are intentionally never sent
        # to OpenAI-compatible endpoints — they are blockers for reasoning
        # models and the server's own default is better for large batches.)
        self._openai_supports_temperature = not _is_reasoning_model(model_name)

    def _initialize_client(self):
        if self._client_initialized:
            return

        # Per-batch HTTP timeout (seconds). Reasoning models can be slow but
        # we cap requests so the GUI never hangs indefinitely on a stuck call.
        request_timeout = float(
            (self.extra_settings or {}).get("request_timeout", 300)
        )

        if self.api_provider == "OpenAI GPT":
            import openai
            self._client = openai.OpenAI(api_key=self.api_key, timeout=request_timeout)
        elif self.api_provider == "OpenRouter":
            import openai
            self._client = openai.OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.api_key,
                timeout=request_timeout,
            )
        elif self.api_provider == "Custom (OpenAI-Compatible)":
            # Flexible endpoint: user provides any OpenAI-compatible base_url.
            # Works with OpenRouter, Together, Groq, vLLM, Ollama, LM Studio, llama.cpp, etc.
            import openai
            base_url = (self.extra_settings or {}).get("base_url", "").strip()
            if not base_url:
                raise ValueError(
                    "Custom provider requires a 'base_url' (e.g. http://localhost:8080/v1 or https://api.groq.com/openai/v1)."
                )
            # Some self-hosted endpoints reject empty api_key; use a placeholder when blank.
            self._client = openai.OpenAI(
                base_url=base_url,
                api_key=self.api_key or "not-needed",
                timeout=request_timeout,
            )
        elif self.api_provider == "Google Gemini":
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            if not self.model_name:
                raise ValueError("A model must be selected for Google Gemini.")
            self._client = genai.GenerativeModel(self.model_name)
        elif self.api_provider == "Local Models":
            if self.local_backend == "Llama.cpp":
                # Start the llama-server for the specified model with GPU support
                if not self.local_model_manager.start_model_server(self.model_name, context_size=4096, gpu_layers=-1):
                    raise RuntimeError(f"Failed to start llama-server for model '{self.model_name}'")
                # Create HTTP client to connect to the server
                self._client = self._create_local_client(base_url="http://localhost:8080/v1")
            elif self.local_backend == "LM Studio":
                self._client = self._create_local_client()
        elif self.api_provider == "HuggingFace":
            # Hugging Face engine uses local transformers and does not require a persistent client.
            # The actual engine will be imported and initialized in translate_entries.
            self._client = None
        elif self.api_provider == "Argos Translate":
            # Argos Translate is an offline, local package-based engine. No persistent client required.
            # Actual translation calls will be delegated to the argos engine module when used.
            self._client = None
        else:
            raise ValueError(f"Unsupported API provider: {self.api_provider}")
        self._client_initialized = True

    def _create_local_client(self, base_url="http://localhost:1234/v1"):
        import requests
        try:
            requests.get(f"{base_url.replace('/v1', '')}/v1/models", timeout=5).raise_for_status()
            class LocalClient:
                def __init__(self, base_url):
                    self.chat = type("Chat", (), {"completions": type("Completions", (), {"create": self._create})})()
                    self.base_url = base_url
                def _create(self, **kwargs):
                    if 'model' in kwargs: del kwargs['model']
                    response = requests.post(f"{self.base_url}/chat/completions", json=kwargs, timeout=60)
                    response.raise_for_status()
                    return response.json()
            return LocalClient(base_url)
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Failed to connect to local server at {base_url}. Details: {e}")

    def translate_entries(self, entries, source_lang, target_lang, context=None,
                         progress_callback=None, surrounding_context=None,
                         all_po_entries=None, po_entries_positions=None,
                         context_previous_size=0, context_next_size=0,
                         cancel_check=None):
        """
        High-level entry point for translating a list of entries.
        If the configured provider is Argos Translate, delegate to the argos-specific path
        which performs offline, package-based translations (per-entry).
        Otherwise retain existing batch-based LLM processing.

        ``cancel_check`` is an optional zero-arg callable returning ``True`` when
        the user has requested cancellation. It is polled between entries
        (Argos) and between batches (LLM). On cancel the loop stops and whatever
        has already been translated is returned, with ``usage['cancelled']``
        set to ``True`` so partial work is never lost.
        """
        self._initialize_client() # Ensure client is initialized before translation

        # Argos offline path: delegate to the argos_engine module (keeps AITranslator small)
        if self.api_provider == "Argos Translate":
            try:
                from mutt.engines import argos_engine
            except Exception:
                argos_engine = None # Ensure argos_engine is None if import fails

            if not argos_engine or not getattr(argos_engine, "ARGOS_AVAILABLE", False):
                raise RuntimeError(
                    "Argos Translate engine is not available. Install `argostranslate` and/or ensure the engines package is present."
                )
            # Resolve strategy from extra settings. Default to 'prompt_install' so the UI can handle it.
            strategy = self.extra_settings.get("argos_strategy", "prompt_install") if isinstance(self.extra_settings, dict) else "prompt_install"
            # Same job expansion as the LLM path: a plural entry needs both its
            # singular and plural source translated, one per msgstr[n].
            items = []
            for entry in entries:
                if entry.get('obsolete'):
                    continue
                items.append((entry, None if not entry.get('source_plural') else 0))
                if entry.get('source_plural'):
                    items.append((entry, 1))
            total = len(items)
            translated_texts = []
            cancelled = False
            for idx, (entry, form) in enumerate(items):
                if cancel_check and cancel_check():
                    cancelled = True
                    break
                src_text = entry.get('msgid', '') if form in (None, 0) else entry.get('source_plural', '')
                try:
                    # The pivot_order is no longer needed, as the new engine handles it.
                    translated = argos_engine.translate_text(src_text, source_lang, target_lang, strategy=strategy)
                except getattr(argos_engine, "ArgosPackageMissingError", Exception) as e:
                    # This is the specific error we want the UI to handle. Re-raise it directly
                    # so the on_result handler can trigger the install flow.
                    raise e
                except Exception as e:
                    # For any other unexpected error, wrap it for context.
                    raise RuntimeError(f"An unexpected Argos Translate error occurred for entry index {idx}: {e}") from e
                translated_texts.append(translated)
                if progress_callback:
                    progress_callback(idx + 1, total)
            # Merge back by position (not by msgid) to handle duplicate source
            # strings. Bounded by what was actually translated so a cancelled
            # run keeps its partial output instead of raising IndexError.
            result_entries = [dict(entry) for entry in entries]
            entry_positions = {id(entry): idx for idx, entry in enumerate(entries)}
            for k, (entry, form) in enumerate(items):
                if k >= len(translated_texts):
                    break
                target = result_entries[entry_positions[id(entry)]]
                target['fuzzy'] = False  # updated against the current source
                if form is None:
                    target['msgstr'] = translated_texts[k]
                elif form == 0:
                    set_target_for_form(target, 0, translated_texts[k])
                else:
                    for plural_form in plural_forms(target)[1:]:
                        set_target_for_form(target, plural_form, translated_texts[k])
            return result_entries, {"prompt_tokens": 0, "completion_tokens": 0, "cancelled": cancelled}
 
        # Existing LLM/batch path (unchanged)
        # Hugging Face engine path: delegate to hf_engine module
        if self.api_provider == "HuggingFace":
            try:
                from mutt.engines import hf_engine
            except Exception:
                hf_engine = None # Ensure hf_engine is None if import fails

            if not hf_engine or not getattr(hf_engine, "HF_AVAILABLE", False):
                raise RuntimeError("Hugging Face engine is not available.")
            try:
                hf_config = {
                    "model": self.extra_settings.get("api_model") if isinstance(self.extra_settings, dict) else None,
                    "device": self.extra_settings.get("device", "cpu") if isinstance(self.extra_settings, dict) else "cpu",
                    "batch_size": self.batch_size,
                    "cache_dir": self.extra_settings.get("hf_cache_dir") if isinstance(self.extra_settings, dict) else None
                }
                engine = hf_engine.HuggingFaceEngine(config=hf_config)
                return engine.translate_entries(entries, source_lang, target_lang, progress_callback=progress_callback)
            except Exception as e:
                raise RuntimeError(f"Hugging Face translation failed: {e}") from e

        result_entries = [dict(entry) for entry in entries]
        # One "job" per string the model must translate. A plural entry
        # contributes two — the singular msgid and the msgid_plural — because
        # gettext keeps a separate msgstr[n] for each. Translating only msgid
        # used to write a target that polib then discarded on save, silently
        # losing every plural translation.
        jobs = []
        for i, entry in enumerate(entries):
            if entry.get('obsolete'):
                continue
            pos = (po_entries_positions[i]
                   if po_entries_positions is not None and i < len(po_entries_positions)
                   else None)
            if entry.get('source_plural'):
                jobs.append({'index': i, 'form': 0, 'text': entry.get('msgid', ''), 'pos': pos, 'entry': entry})
                jobs.append({'index': i, 'form': 1, 'text': entry.get('source_plural', ''), 'pos': pos, 'entry': entry})
            else:
                jobs.append({'index': i, 'form': None, 'text': entry.get('msgid', ''), 'pos': pos, 'entry': entry})

        if not jobs:
            return result_entries, {"prompt_tokens": 0, "completion_tokens": 0}

        # Parallel list of positions in ``all_po_entries`` for each job.
        # Allows a correct per-sub-batch context window even when entries have
        # been filtered (non-contiguous) or share duplicate msgids.
        item_positions = None
        context_enabled = bool(
            all_po_entries is not None
            and po_entries_positions is not None
            and (context_previous_size > 0 or context_next_size > 0)
        )
        if context_enabled:
            job_positions = [j['pos'] for j in jobs]
            if all(p is not None for p in job_positions):
                item_positions = job_positions
            else:
                # Positions didn't resolve — don't risk wrong anchors, disable.
                context_enabled = False

        items_to_translate = jobs
        msgids_to_translate = [j['text'] for j in jobs]
        final_translated_texts = []
        total_prompt_tokens, total_completion_tokens = 0, 0
        effective_batch_size = self.batch_size

        print(f"Processing {len(msgids_to_translate)} entries in batches of up to {effective_batch_size} (Token Limit: {self.max_batch_tokens})")

        cancelled = False
        for i in range(0, len(items_to_translate), effective_batch_size):
            if cancel_check and cancel_check():
                cancelled = True
                break
            primary_end = min(i + effective_batch_size, len(items_to_translate))
            batch_jobs = items_to_translate[i:primary_end]
            batch_msgids = msgids_to_translate[i:primary_end]
            estimated_tokens = sum(len(text.split()) * 1.5 for text in batch_msgids) + 500

            if estimated_tokens > self.max_batch_tokens:
                sub_batch_size = max(1, int(len(batch_msgids) * (self.max_batch_tokens / estimated_tokens) * 0.9))
                slices = [(j, min(j + sub_batch_size, len(batch_msgids)))
                          for j in range(0, len(batch_msgids), sub_batch_size)]
                print(f"Batch from index {i} is too large ({int(estimated_tokens)} tokens), splitting into {len(slices)} smaller batches.")
            else:
                slices = [(0, len(batch_msgids))]

            for sub_start, sub_end in slices:
                sub_msgids = batch_msgids[sub_start:sub_end]
                print(f"Processing batch of {len(sub_msgids)} entries.")

                window = None
                if context_enabled and item_positions is not None:
                    positions = item_positions[i + sub_start:i + sub_end]
                    if positions:
                        min_pos = min(positions)
                        max_pos = max(positions)
                        total_all = len(all_po_entries)
                        window = {
                            "previous": all_po_entries[max(0, min_pos - context_previous_size):min_pos],
                            "next":     all_po_entries[max_pos + 1:min(total_all, max_pos + 1 + context_next_size)],
                        }

                sub_entries = [j['entry'] for j in batch_jobs[sub_start:sub_end]]
                translated_sub_batch, usage = self._process_batch(
                    sub_msgids, source_lang, target_lang, context, window,
                    batch_entries=sub_entries,
                )
                final_translated_texts.extend(translated_sub_batch)
                total_prompt_tokens += usage.get('prompt_tokens', 0)
                total_completion_tokens += usage.get('completion_tokens', 0)

            if progress_callback:
                progress_callback(primary_end, len(msgids_to_translate))

            time.sleep(1)

        # Merge back by job (not by msgid) to handle duplicate source strings.
        # Bounded by what was actually translated so a cancelled run keeps its
        # partial output instead of raising IndexError.
        for k, job in enumerate(jobs):
            if k >= len(final_translated_texts):
                break
            target = result_entries[job['index']]
            # Only an entry the model actually answered loses its fuzzy mark;
            # a cancelled run's untouched entries stay flagged as outdated.
            target['fuzzy'] = False
            text = final_translated_texts[k]
            if job['form'] is None:
                target['msgstr'] = text
            elif job['form'] == 0:
                set_target_for_form(target, 0, text)
            else:
                # gettext gives the source only two forms; every target form
                # beyond the first is seeded from msgid_plural. Languages with
                # more than two forms get a sane starting point the translator
                # then adjusts per form in the review panel.
                for form in plural_forms(target)[1:]:
                    set_target_for_form(target, form, text)

        return result_entries, {"prompt_tokens": total_prompt_tokens, "completion_tokens": total_completion_tokens, "cancelled": cancelled}

    # FIX: Restored the robust, multi-line prompt. This is the critical change.
    def _get_system_prompt(self):
        return (
            "You are a professional, accurate translation engine. "
            "You will be given a user prompt containing a JSON object with a key 'texts_to_translate'. "
            "You MUST respond with a single, valid JSON object and nothing else. "
            "The JSON object must have one key: 'translated_texts'. "
            "The value of 'translated_texts' must be a JSON array of strings, with each string being the translation. "
            "Do not add any explanations, apologies, or introductory text. Only the JSON object is allowed."
        )

    # FIX: Restored a clearer, more structured user prompt.
    def _build_user_prompt(self, batch_texts, source_lang, target_lang, context,
                           surrounding_context=None, batch_entries=None):
        """Builds the user-facing prompt with instructions and data, including
        surrounding context and any per-string translator/extractor comments."""
        prompt_lines = [
            f"Translate the following JSON array of strings from '{source_lang}' to '{target_lang}'.",
            "The translated strings in the output JSON array MUST be in the exact same order as the input array.",
        ]
        if context:
            prompt_lines.append(f"Use this context for all translations: {context}")

        # Per-string comments from the source file. These are the notes the
        # original developers and translators wrote precisely to disambiguate
        # these strings, so they are worth the tokens.
        if batch_entries:
            note_lines = []
            for position, entry in enumerate(batch_entries):
                if not isinstance(entry, dict):
                    continue
                guidance = guidance_notes(entry)
                outdated = (entry.get('msgstr') or '').strip() if entry.get('fuzzy') else ''
                if outdated:
                    # A fuzzy entry's old translation is the best starting point:
                    # update it to the new source, don't translate from scratch.
                    old_source = entry.get('polib_previous_msgid')
                    hint = f"outdated translation \"{outdated}\""
                    if old_source:
                        hint += f" was made for the old source \"{old_source}\""
                    hint += ("; the source has changed since. Update it to match the "
                             "current source, keeping its wording and terminology "
                             "where they still fit")
                    guidance = f"{guidance} | {hint}" if guidance else hint
                if guidance:
                    note_lines.append(f"- Item {position}: {guidance}")
            if note_lines:
                prompt_lines.append(
                    "\nNotes for specific items below (index into the input array). "
                    "Follow them; they come from the file's own translator and developer comments:"
                )
                prompt_lines.extend(note_lines)

        # Approved translations from the active termbase / TM. Advisory, not
        # a find-and-replace: the same term is translated differently in
        # different contexts, so the model gets the last word.
        if self.glossary:
            batch_lower = [t.lower() for t in batch_texts if t]
            relevant = [(src, tgt) for src, tgt in self.glossary.items()
                        if any(src.lower() in text for text in batch_lower)]
            relevant.sort(key=lambda pair: len(pair[0]), reverse=True)
            if relevant:
                prompt_lines.append(
                    "\nPreviously approved translations for terms appearing below. "
                    "Prefer them for consistency, but override any that do not fit "
                    "this context:"
                )
                for src, tgt in relevant[:40]:
                    prompt_lines.append(f"- \"{src}\" -> \"{tgt}\"")

        if surrounding_context:
            # ``surrounding_context`` may be either the modern dict form
            # (``{"previous": [...], "next": [...]}`` — set by
            # ``translate_entries``) or a legacy flat list of entry dicts.
            # We normalise before rendering.
            if isinstance(surrounding_context, dict):
                previous_entries = list(surrounding_context.get("previous") or [])
                next_entries = list(surrounding_context.get("next") or [])
            else:
                # Legacy: infer by msgstr presence (less reliable, kept for
                # backward compatibility with any external caller).
                previous_entries = [e for e in surrounding_context
                                    if e.get('msgstr')]
                next_entries = [e for e in surrounding_context
                                if not e.get('msgstr')]

            if previous_entries:
                prompt_lines.append(
                    "\nFor context, here are the entries immediately preceding the ones to translate:"
                )
                for entry in previous_entries:
                    target = entry.get('msgstr') or ''
                    if target:
                        prompt_lines.append(
                            f"- Source: \"{entry.get('msgid', '')}\" -> Target: \"{target}\""
                        )
                    else:
                        prompt_lines.append(
                            f"- Source: \"{entry.get('msgid', '')}\" (not yet translated)"
                        )

            if next_entries:
                prompt_lines.append(
                    "\nAnd here are the source texts of the entries immediately following:"
                )
                for entry in next_entries:
                    prompt_lines.append(f"- Source: \"{entry.get('msgid', '')}\"")

        prompt_lines.append("\nInput JSON:")
        input_json = json.dumps({"texts_to_translate": batch_texts}, ensure_ascii=False)
        prompt_lines.append(input_json)

        return "\n".join(prompt_lines)

    @staticmethod
    def _repair_model_json(text: str) -> str:
        """Fix the two ways models garble a long JSON response mid-stream:
        a raw newline/tab left unescaped inside a string, and a stray '.'
        or ';' dropped between array elements. String-aware, so neither
        repair can touch the translated text itself.
        shortcut: only these two glitches, widen when a new one shows up.
        """
        backslash = chr(92)
        escapes = {"\n": backslash + "n", "\r": backslash + "r", "\t": backslash + "t"}
        out = []
        in_string = False
        escape = False
        for ch in text:
            if in_string:
                if escape:
                    escape = False
                elif ch == backslash:
                    escape = True
                elif ch == '"':
                    in_string = False
                if ord(ch) < 0x20:
                    out.append(escapes.get(ch, " "))
                    continue
            elif ch == '"':
                in_string = True
            elif ch in ".;":
                # Junk where only a value may start, e.g. '"a",. "b"'.
                prev = next((c for c in reversed(out) if not c.isspace()), "")
                if prev in ",[{:":
                    continue
            out.append(ch)
        return "".join(out)

    def _extract_json_from_text(self, text: str) -> str:
        """
        Attempt to extract a valid JSON substring from the given text.
        Tries a direct json.loads first; if that fails it searches for the
        first well-formed JSON object or array by matching braces/brackets
        while taking string escaping into account.
        Raises json.JSONDecodeError if no valid JSON can be found.
        """
        text = (text or "").strip()
        # Quick attempt: maybe it's already valid JSON
        try:
            json.loads(text)
            return text
        except Exception:
            pass

        # Second attempt: repair the usual mid-stream corruption, then retry.
        repaired = self._repair_model_json(text)
        if repaired != text:
            try:
                json.loads(repaired)
                return repaired
            except Exception:
                # Keep the repair for the brace search below — it can only help.
                text = repaired

        # Search for a JSON object or array starting point
        for start_char, end_char in (('{', '}'), ('[', ']')):
            start = text.find(start_char)
            if start == -1:
                continue
            depth = 0
            in_string = False
            escape = False
            for i in range(start, len(text)):
                ch = text[i]
                if in_string:
                    if escape:
                        escape = False
                    elif ch == '\\':
                        escape = True
                    elif ch == '"':
                        in_string = False
                else:
                    if ch == '"':
                        in_string = True
                    elif ch == start_char:
                        depth += 1
                    elif ch == end_char:
                        depth -= 1
                        if depth == 0:
                            candidate = text[start:i+1]
                            try:
                                json.loads(candidate)
                                return candidate
                            except Exception:
                                # continue searching if this candidate isn't valid
                                break

        # Fallback: try a loose regex to capture something that looks like JSON
        m = re.search(r'(\{(?:.|\s)*\}|\[(?:.|\s)*\])', text)
        if m:
            cand = m.group(1)
            try:
                json.loads(cand)
                return cand
            except Exception:
                pass

        # As a last resort raise a JSONDecodeError to be handled by caller
        raise json.JSONDecodeError("Could not extract a valid JSON object/array from the model response", text, 0)

    # A batch that died this way is worth splitting and retrying; anything
    # else (auth, quota, network) would just fail again, twice as often.
    _SPLITTABLE_ERROR_MARKERS = (
        "failed to extract json", "malformed list", "empty response",
        "context length", "context_length_exceeded", "maximum context",
        # A reply cut off at the model's output limit is the plainest
        # "batch too big" signal there is; it used to kill the whole run.
        "output-token limit",
    )

    # Four halvings turn a 1000-entry batch into ~60 and cost at most ~30
    # extra calls; past that the model, not the batch size, is the problem.
    _MAX_BATCH_SPLITS = 4

    def _process_batch(self, batch_texts, source_lang, target_lang, context,
                       surrounding_context=None, batch_entries=None, _depth=0):
        """Translate one batch, halving it and retrying when the model
        garbles a response that is too long to come back intact."""
        try:
            return self._process_batch_once(batch_texts, source_lang, target_lang,
                                            context, surrounding_context, batch_entries)
        except Exception as exc:
            msg = str(exc).lower()
            if (len(batch_texts) < 2 or _depth >= self._MAX_BATCH_SPLITS
                    or not any(m in msg for m in self._SPLITTABLE_ERROR_MARKERS)):
                raise
            mid = len(batch_texts) // 2
            print(f"Batch of {len(batch_texts)} failed ({exc}) — retrying as two halves.")
            texts = []
            usage = {"prompt_tokens": 0, "completion_tokens": 0}
            for lo, hi in ((0, mid), (mid, len(batch_texts))):
                part_texts, part_usage = self._process_batch(
                    batch_texts[lo:hi], source_lang, target_lang, context,
                    surrounding_context,
                    batch_entries[lo:hi] if batch_entries else None,
                    _depth + 1,
                )
                texts.extend(part_texts)
                usage["prompt_tokens"] += part_usage.get("prompt_tokens", 0)
                usage["completion_tokens"] += part_usage.get("completion_tokens", 0)
            return texts, usage

    def _process_batch_once(self, batch_texts, source_lang, target_lang, context,
                            surrounding_context=None, batch_entries=None):
        user_prompt = self._build_user_prompt(batch_texts, source_lang, target_lang, context,
                                              surrounding_context, batch_entries)
        system_prompt = self._get_system_prompt()

        try:
            response_text, usage = self._execute_prompt_with_usage(system_prompt, user_prompt)

            # Common cleanup for fenced code blocks used by some models
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            # If after stripping, the response is empty, it's a failure.
            if not response_text:
                raise ValueError("AI returned an empty response.")

            # Try to robustly extract valid JSON from the model output.
            try:
                json_payload = self._extract_json_from_text(response_text)
            except json.JSONDecodeError as jde:
                # Save the raw response for debugging and raise a helpful error.
                log_filename = "ai_response_debug.log"
                with open(log_filename, "w", encoding="utf-8") as f:
                    f.write(response_text)
                error_message = (
                    f"Failed to extract JSON from model response: {jde}. "
                    f"Raw response saved to '{log_filename}'."
                )
                print(error_message)
                raise ValueError(error_message) from jde

            translated_batch_json = json.loads(json_payload)
            translated_texts = translated_batch_json.get("translated_texts", [])

            expected_count = len(batch_texts)
            if isinstance(translated_texts, list) and len(translated_texts) == expected_count:
                return translated_texts, usage

            # Heuristic filtering: remove items that look diagnostic or not like proper translations.
            def likely_translation(s: str) -> bool:
                if not isinstance(s, str):
                    return False
                s_stripped = s.strip()
                if len(s_stripped) == 0:
                    return False
                # Reject common diagnostic tokens and phrases (multilingual)
                reject_patterns = [
                    r'(?i)error', r'(?i)hata', r'(?i)token', r'(?i)glossary', r'(?i)chunk',
                    r'(?i)youtube', r'%\(', r'AI süreci', r'MAX_TOKENS', r'Video', r'analiz', r'YouTube'
                ]
                for pat in reject_patterns:
                    if re.search(pat, s_stripped):
                        return False
                # Accept reasonably short strings or sentences
                if len(s_stripped.splitlines()) > 3:
                    return False
                return True

            filtered = [s for s in translated_texts if likely_translation(s)]
            if len(filtered) == expected_count:
                print("Filtered model output matched expected count after removing diagnostics.")
                return filtered, usage

            # If counts mismatch, attempt a strict retry that forces pure JSON with exact length.
            print(f"AI returned {len(translated_texts)} items but expected {expected_count}. Attempting strict JSON-only retry.")
            strict_system = (
                "Output MUST be a single valid JSON object and nothing else. "
                "The object must have a single key: 'translated_texts' whose value is an array with exactly "
                f"{expected_count} strings. Do not include any commentary, metadata, or code fences."
            )
            strict_user = json.dumps({"texts_to_translate": batch_texts}, ensure_ascii=False)
            try:
                strict_response_text, strict_usage = self._execute_prompt_with_usage(strict_system, strict_user)
                if strict_response_text.startswith("```json"):
                    strict_response_text = strict_response_text[7:]
                if strict_response_text.endswith("```"):
                    strict_response_text = strict_response_text[:-3]
                strict_response_text = strict_response_text.strip()

                strict_payload = self._extract_json_from_text(strict_response_text)
                strict_json = json.loads(strict_payload)
                strict_texts = strict_json.get("translated_texts", [])

                if isinstance(strict_texts, list) and len(strict_texts) == expected_count:
                    # Merge usage conservatively
                    try:
                        usage["prompt_tokens"] = usage.get("prompt_tokens", 0) + strict_usage.get("prompt_tokens", 0)
                        usage["completion_tokens"] = usage.get("completion_tokens", 0) + strict_usage.get("completion_tokens", 0)
                    except Exception:
                        pass
                    return strict_texts, usage

                # If strict retry returned more items, truncate to expected_count.
                if isinstance(strict_texts, list) and len(strict_texts) > expected_count:
                    print(f"Strict retry returned {len(strict_texts)} items; truncating to the first {expected_count} items.")
                    truncated = strict_texts[:expected_count]
                    try:
                        usage["prompt_tokens"] = usage.get("prompt_tokens", 0) + strict_usage.get("prompt_tokens", 0)
                        usage["completion_tokens"] = usage.get("completion_tokens", 0) + strict_usage.get("completion_tokens", 0)
                    except Exception:
                        pass
                    return truncated, usage

            except Exception as retry_exc:
                # Log retry failure for debugging and continue to salvage original output if possible
                print(f"Strict JSON retry failed: {retry_exc}")

            # Salvage: if original had more items than expected, truncate and return (but log)
            if isinstance(translated_texts, list) and len(translated_texts) > expected_count:
                print(f"Warning: returning the first {expected_count} items from a response that contained {len(translated_texts)} items.")
                salvaged = translated_texts[:expected_count]
                log_filename = "ai_response_debug.log"
                with open(log_filename, "w", encoding="utf-8") as f:
                    f.write(response_text)
                return salvaged, usage

            # Cannot salvage: save raw response and raise
            error_message = f"AI returned a malformed list. Expected {expected_count} items, but got {len(translated_texts)}. Cannot proceed with this batch."
            print(error_message)
            log_filename = "ai_response_debug.log"
            with open(log_filename, "w", encoding="utf-8") as f:
                f.write(response_text)
            raise ValueError(error_message)
        except Exception as e:
            # Any exception here is critical for the batch - log and re-raise with context.
            log_filename = "ai_response_debug.log"
            try:
                with open(log_filename, "w", encoding="utf-8") as f:
                    f.write(response_text if 'response_text' in locals() else str(e))
            except Exception:
                pass

            error_message = (
                f"Batch processing failed due to a critical error: {e}. "
                f"The full, malformed AI response has been saved to '{log_filename}' for debugging."
            )
            print(error_message)
            raise ValueError(error_message) from e


    # ------------------------------------------------------------------
    # OpenAI-compatible chat-completion helper
    # ------------------------------------------------------------------
    def _build_openai_kwargs(self, messages):
        """Build kwargs for ``client.chat.completions.create``.

        NOTE: ``max_tokens`` / ``max_completion_tokens`` are intentionally
        NOT sent. On reasoning models they are blockers (either rejected
        outright or they truncate the JSON response mid-structure), and
        the server's own default is a far better choice for large batches.
        ``temperature`` is only sent when the model accepts it.
        """
        kwargs = {"model": self.model_name, "messages": messages}
        if self._openai_supports_temperature:
            kwargs["temperature"] = self.temperature
        return kwargs

    # Error patterns that indicate a permanent, client-side problem — no point retrying.
    _FATAL_ERROR_MARKERS = (
        "authentication", "api key", "invalid_api_key", "permission",
        "not authorized", "unauthorized", "model_not_found",
        "insufficient_quota", "billing", "quota", "context length",
        "context_length_exceeded", "maximum context",
    )

    def _is_transient_error(self, exc: Exception) -> bool:
        """Heuristic: True when the error looks like a server/network blip
        worth retrying once (malformed JSON body, 5xx, connection reset,
        timeouts) rather than a fatal client-side problem."""
        msg = str(exc).lower()
        if any(marker in msg for marker in self._FATAL_ERROR_MARKERS):
            return False
        transient_markers = (
            "expecting value",        # json.JSONDecodeError from the SDK
            "unterminated string",    # json.JSONDecodeError variant
            "delimiter",              # json.JSONDecodeError variant
            "internal server error", "bad gateway", "service unavailable",
            "gateway timeout", "connection reset", "connection aborted",
            "read timed out", "timed out", "timeout",
            "502", "503", "504", "520", "521", "522", "524",
        )
        return any(marker in msg for marker in transient_markers)

    def _openai_chat_create(self, messages):
        """Call the OpenAI-compatible client.

        * If the server returns a 400 saying ``temperature`` isn't supported,
          retry once without ``temperature`` and remember the decision so
          subsequent calls skip it straight away.
        * On transient server/network failures (malformed JSON body, 5xx,
          timeouts), retry once after a short backoff before surfacing.
        """
        max_attempts = 3
        transient_retried = False
        base_url = getattr(self._client, "base_url", None)
        endpoint_tag = f" via {base_url}" if base_url and "api.openai.com" not in str(base_url) else ""
        for attempt in range(max_attempts):
            try:
                temp_state = "on" if self._openai_supports_temperature else "off"
                t0 = time.time()
                tag = (
                    f"[{self.api_provider}] {self.model_name}{endpoint_tag} "
                    f"attempt={attempt + 1} temp={temp_state}"
                )
                _log(f"{tag.replace('] ', '] -> ', 1)} messages={len(messages)}")
                resp = self._client.chat.completions.create(
                    **self._build_openai_kwargs(messages)
                )
                _log(f"[{self.api_provider}] <- response in {time.time() - t0:.1f}s")
                # Capture the raw response body to openai_responses.log for
                # post-mortem debugging (truncated at 64k chars).
                try:
                    body = resp.model_dump_json()
                except Exception:
                    try:
                        body = json.dumps(resp, default=str)
                    except Exception:
                        body = str(resp)
                _log_raw_response(f"OK  {tag}", body)
                return resp
            except Exception as e:
                msg = str(e).lower()
                if (
                    self._openai_supports_temperature
                    and "temperature" in msg
                    and (
                        "unsupported" in msg
                        or "not supported" in msg
                        or "does not support" in msg
                    )
                ):
                    self._openai_supports_temperature = False
                    _log(
                        f"[{self.api_provider}] server rejected temperature; retrying without it."
                    )
                    continue
                if not transient_retried and self._is_transient_error(e):
                    transient_retried = True
                    _log(
                        f"[{self.api_provider}] transient failure ({e}); backing off 3s and retrying once."
                    )
                    time.sleep(3)
                    continue
                _log(f"[{self.api_provider}] !! request failed: {e}")
                _log_raw_response(
                    f"ERR {self.api_provider} {self.model_name}{endpoint_tag} "
                    f"attempt={attempt + 1}",
                    _extract_error_body(e),
                )
                raise
        # Loop exhausted without returning — propagate whatever comes next.
        return self._client.chat.completions.create(
            **self._build_openai_kwargs(messages)
        )

    @staticmethod
    def _extract_openai_usage(response):
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        u = getattr(response, "usage", None)
        if u is not None:
            usage["prompt_tokens"] = getattr(u, "prompt_tokens", 0) or 0
            usage["completion_tokens"] = getattr(u, "completion_tokens", 0) or 0
        return usage

    @staticmethod
    def _check_finish_reason(response) -> None:
        """Raise a clear error when the model truncated its own output.

        ``finish_reason == "length"`` (OpenAI / OpenRouter / Gemini via
        gateway) or ``"MAX_TOKENS"`` (native Gemini) means the model hit
        an output-token cap mid-response — so the JSON body we're about
        to parse is guaranteed to be incomplete.
        """
        choices = getattr(response, "choices", None) or []
        if not choices:
            return
        reason = getattr(choices[0], "finish_reason", None)
        if not reason:
            return
        reason_lc = str(reason).lower()
        if reason_lc in ("length", "max_tokens"):
            raise ValueError(
                "Model truncated its response because it hit an output-token "
                "limit. Your batch is too large for this model's default "
                "output budget. Lower 'Batch Size' in API Setup -> Basic "
                "Settings (try 20-50) and retry."
            )

    def _execute_prompt_with_usage(self, system_prompt, user_prompt):
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

        if self.api_provider in ["OpenAI GPT", "OpenRouter", "Custom (OpenAI-Compatible)"]:
            response = self._openai_chat_create(messages)
            usage.update(self._extract_openai_usage(response))
            self._check_finish_reason(response)
            return response.choices[0].message.content, usage

        # For Gemini, combining prompts is often more effective
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        if self.api_provider == "Google Gemini":
            response = self._client.generate_content(full_prompt)
            if hasattr(response, 'usage_metadata'): usage.update({"prompt_tokens": response.usage_metadata.prompt_token_count, "completion_tokens": response.usage_metadata.candidates_token_count})
            return response.text, usage

        elif self.api_provider == "Local Models":
            if self.local_backend == "Llama.cpp":
                # Use the LocalModelManager's server API. Do NOT pass
                # max_tokens — rely on the server's own default.
                response = self.local_model_manager.create_chat_completion(
                    messages, temperature=self.temperature
                )
                if "usage" in response: usage.update(response["usage"])
                return response["choices"][0]["message"]["content"], usage
            else:
                response = self._openai_chat_create(messages)
                usage.update(self._extract_openai_usage(response))
                self._check_finish_reason(response)
                return response.choices[0].message.content, usage

        return "", usage

    def _execute_single_prompt(self, prompt):
        self._initialize_client() # Ensure client is initialized before executing single prompt
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        try:
            if self.api_provider in ["OpenAI GPT", "OpenRouter", "Custom (OpenAI-Compatible)"]:
                response = self._openai_chat_create([{"role": "user", "content": prompt}])
                usage.update(self._extract_openai_usage(response))
                self._check_finish_reason(response)
                return response.choices[0].message.content.strip(), usage
            elif self.api_provider == "Google Gemini":
                response = self._client.generate_content(prompt)
                if hasattr(response, 'usage_metadata'): usage.update({"prompt_tokens": response.usage_metadata.prompt_token_count, "completion_tokens": response.usage_metadata.candidates_token_count})
                return response.text.strip(), usage
            elif self.api_provider == "Local Models":
                messages = [{"role": "user", "content": prompt}]
                if self.local_backend == "Llama.cpp":
                    # Use the LocalModelManager's server API. Do NOT pass
                    # max_tokens — rely on the server's own default.
                    response = self.local_model_manager.create_chat_completion(
                        messages, temperature=self.temperature
                    )
                    if "usage" in response: usage.update(response["usage"])
                    return response["choices"][0]["message"]["content"].strip(), usage
                else:
                    response = self._openai_chat_create(messages)
                    usage.update(self._extract_openai_usage(response))
                    self._check_finish_reason(response)
                    return response.choices[0].message.content.strip(), usage
        except Exception as e:
            print(f"Error executing single prompt: {e}")
            return f"[Error: {e}]", usage
        return "[Error: Provider not supported]", usage

    def __del__(self):
        """Cleanup method to stop the server when the translator is destroyed"""
        if hasattr(self, 'local_model_manager') and self.api_provider == "Local Models" and self.local_backend == "Llama.cpp":
            self.local_model_manager.stop_model_server()

    def is_local_server_running(self):
        """Check if the local server is running"""
        if self.api_provider == "Local Models" and self.local_backend == "Llama.cpp":
            return self.local_model_manager.is_model_server_running()
        return False

    def get_server_info(self):
        """Get information about the running server"""
        if self.api_provider == "Local Models" and self.local_backend == "Llama.cpp":
            return self.local_model_manager.get_model_server_info()
        return {}