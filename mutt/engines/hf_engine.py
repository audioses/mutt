"""mutt/engines/hf_engine.py
Hugging Face translation engine for MUTT.
"""

import os
import logging
from typing import List, Optional, Dict

# HF_AVAILABLE flag and imports are now managed dynamically by _import_hf()
logger = logging.getLogger(__name__)

# Global variables for lazy loading
HF_AVAILABLE = False
pipeline = None
AutoTokenizer = None
AutoModelForSeq2SeqLM = None
list_models = None
snapshot_download = None
torch = None

def _import_hf():
    """Helper to import Hugging Face modules and set HF_AVAILABLE."""
    global HF_AVAILABLE, pipeline, AutoTokenizer, AutoModelForSeq2SeqLM, list_models, snapshot_download, torch
    if not HF_AVAILABLE:
        try:
            from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
            from huggingface_hub import list_models, snapshot_download
            import torch
            HF_AVAILABLE = True
        except Exception as e:
            HF_AVAILABLE = False
            logger.warning(f"Hugging Face dependencies not available: {e}")
            raise RuntimeError("Hugging Face dependencies not available. Please install 'transformers' and 'huggingface_hub'.")
    return HF_AVAILABLE


class HFModelManager:
    """Discover, download and manage Hugging Face models."""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir or os.path.join("models", "hf_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

    def search_translation_models(self, query: Optional[str] = None, limit: int = 50):
        """
        Search for translation-capable models on the Hub.
        This version uses the 'search' parameter in list_models for better results.
        """
        _import_hf() # Ensure HF is available
        results = []
        try:
            # Use the 'search' parameter for a more direct query.
            # The 'translation' filter is still useful to narrow down the results.
            models = list_models(search=query, filter="translation", limit=limit)
            for model in models:
                results.append(model.modelId)

            # If the initial search yields no results, try a broader search without the translation filter.
            if not results and query:
                all_models = list_models(search=query, limit=limit)
                for model in all_models:
                    # A simple heuristic to check if it's a translation model
                    if "translation" in model.tags or (model.pipeline_tag and "translation" in model.pipeline_tag):
                         if model.modelId not in results:
                            results.append(model.modelId)
        except Exception as e:
            logger.exception("Hugging Face model search failed: %s", e)

        return results

    def download_model(self, model_id: str, local_dir: Optional[str] = None, allow_patterns: Optional[list] = None):
        """
        Download only the essential files required for runtime inference where possible.

        By default snapshot_download downloads the entire repo snapshot. We can
        significantly reduce disk usage by passing allow_patterns to snapshot_download
        (huggingface_hub supports this parameter) to only fetch files matching the patterns.

        Recommended allow_patterns (best-effort across model types):
          - "config.json"
          - "tokenizer.json"
          - "tokenizer_config.json"
          - "vocab.json"
          - "merges.txt"
          - "sentencepiece.model"
          - "*.bin"              # PyTorch model weights (may be large)
          - "*.safetensors"     # safer format (may be large)
          - "generation_config.json"
          - "special_tokens_map.json"
          - "tokenizer.*"        # other tokenizer ancillary files

        Note: For very large GGUF-style model repos or repos that store large files
        under separate LFS refs, the hub may still fetch large blobs if they match
        the allow_patterns. For some repos the minimal set may still be large.
        """
        _import_hf() # Ensure HF is available
        target_dir = local_dir or self.cache_dir

        # Default allow_patterns if none provided
        if allow_patterns is None:
            allow_patterns = [
                "config.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "vocab.json",
                "merges.txt",
                "sentencepiece.model",
                "generation_config.json",
                "special_tokens_map.json",
                "tokenizer.*",
                "*.bin",
                "*.safetensors",
            ]

        # Use snapshot_download with allow_patterns when available.
        try:
            path = snapshot_download(repo_id=model_id, cache_dir=target_dir, allow_patterns=allow_patterns)
        except TypeError:
            # Older huggingface_hub versions may not support allow_patterns; fallback to full snapshot
            path = snapshot_download(repo_id=model_id, cache_dir=target_dir)
        return path

    def list_cached_models(self):
        """
        Return a list of cached model identifiers by inspecting the cache directory.
        Handles common huggingface_hub snapshot layouts like:
          models--org--repo/... or models--org--repo--subpath
        and also direct repo_id folders. Returns best-effort repo-like identifiers.
        """
        _import_hf() # Ensure HF is available
        results = []
        try:
            for entry in os.listdir(self.cache_dir):
                full = os.path.join(self.cache_dir, entry)
                if not os.path.isdir(full):
                    continue

                # huggingface_hub often names cached folders like: models--org--repo--xyz
                if entry.startswith("models--"):
                    parts = entry.split("--")[1:]
                    if len(parts) >= 2:
                        repo_id = f"{parts[0]}/{parts[1]}"
                    else:
                        repo_id = entry
                    results.append(repo_id)
                    continue

                # If folder contains 'snapshots' or obvious model files, include folder name
                if os.path.isdir(os.path.join(full, "snapshots")):
                    results.append(entry)
                    continue

                # If folder contains any .gguf or model files, include it
                try:
                    for f in os.listdir(full):
                        if f.endswith(".gguf") or f.endswith(".bin") or f.endswith(".pt") or f.endswith(".safetensors"):
                            results.append(entry)
                            break
                except Exception:
                    pass

            # Deduplicate while preserving order
            seen = set(); out = []
            for r in results:
                if r not in seen:
                    seen.add(r); out.append(r)
            return out
        except Exception as e:
            logger.exception("Failed to list cached models: %s", e)
            return []

    def delete_cached_model(self, model_id: str):
        """
        Attempt to delete cached snapshots related to a repo id.
        Performs a best-effort search for directories whose names contain the model_id parts.
        Returns True if one or more directories were removed.
        """
        _import_hf() # Ensure HF is available
        try:
            import shutil
            removed_any = False
            target_parts = model_id.replace("/", "--")
            for entry in os.listdir(self.cache_dir):
                full = os.path.join(self.cache_dir, entry)
                if not os.path.isdir(full):
                    continue
                # direct match attempts
                if model_id in entry or target_parts in entry or entry.startswith("models--") and all(p in entry for p in model_id.split("/")):
                    try:
                        shutil.rmtree(full)
                        removed_any = True
                    except Exception as e:
                        logger.exception("Failed to remove cache folder %s: %s", full, e)
                        # continue trying other candidates
            return removed_any
        except Exception as e:
            logger.exception("Error while attempting to delete cached model '%s': %s", model_id, e)
            return False


class HFTranslator:
    """Loads a model + tokenizer and performs translation via transformers.pipeline."""

    def __init__(self, model_name_or_path: str, device: Optional[str] = None, cache_dir: Optional[str] = None):
        """
        Initialize the HFTranslator.

        Performs a lightweight check for model weights in the cache (best-effort).
        If weights are absent, raise a RuntimeError with an actionable message
        so the UI can prompt the user to download full weights via the manager.
        """
        _import_hf() # Ensure HF is available
        self.model_id = model_name_or_path
        self.cache_dir = cache_dir
        self.device = device

        def _weights_exist(cache_dir: Optional[str], model_id: str) -> bool:
            if not cache_dir or not os.path.isdir(cache_dir):
                return False
            
            # Construct the expected cache path for the model
            model_path_part = "models--" + model_id.replace("/", "--")
            
            # Walk the cache directory to find the model folder
            for entry in os.listdir(cache_dir):
                if entry.startswith(model_path_part):
                    model_path = os.path.join(cache_dir, entry)
                    snapshots_path = os.path.join(model_path, "snapshots")
                    if os.path.isdir(snapshots_path):
                        for snapshot_dir in os.listdir(snapshots_path):
                            snapshot_full_path = os.path.join(snapshots_path, snapshot_dir)
                            if os.path.isdir(snapshot_full_path):
                                for _, _, files in os.walk(snapshot_full_path):
                                    for fname in files:
                                        if fname.endswith((".safetensors", ".bin", ".pt")):
                                            return True
            return False

        has_weights = _weights_exist(self.cache_dir, str(self.model_id))

        use_cuda = False
        if device and device.lower() in ("cuda", "gpu") and torch.cuda.is_available():
            use_cuda = True
        device_arg = 0 if use_cuda else -1

        if not has_weights:
            raise RuntimeError(
                f"Model weights for '{self.model_id}' were not found in the local cache. "
                "Please download full model weights using 'Download by ID' in Manage Hugging Face Models before running inference."
            )
        try:
            self.translator = pipeline("translation", model=self.model_id, tokenizer=self.model_id, device=device_arg)
        except Exception:
            try:
                tokenizer = AutoTokenizer.from_pretrained(self.model_id, cache_dir=self.cache_dir)
                model = AutoModelForSeq2SeqLM.from_pretrained(self.model_id, cache_dir=self.cache_dir)
                self.translator = pipeline("translation", model=model, tokenizer=tokenizer, device=device_arg)
            except Exception as e2:
                logger.exception("Failed to initialize HF translator for %s: %s", self.model_id, e2)
                raise


    def translate(self, texts: List[str], batch_size: int = 8, **kwargs) -> List[str]:
        _import_hf() # Ensure HF is available
        results: List[str] = []
        if not texts:
            return results
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            try:
                outputs = self.translator(batch, **kwargs)
                # pipeline returns list of dicts with 'translation_text' or strings
                for out in outputs:
                    if isinstance(out, dict):
                        results.append(out.get("translation_text", "").strip())
                    else:
                        results.append(str(out).strip())
            except Exception as e:
                logger.exception("Translation failed for batch starting at %d: %s", i, e)
                # on failure, return placeholders to preserve ordering
                results.extend([""] * len(batch))
        return results


class HuggingFaceEngine:
    """High-level engine to orchestrate Hugging Face translations for MUTT."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.cache_dir = self.config.get("cache_dir") or os.path.join("models", "hf_cache")
        self.model_name = self.config.get("model")  # e.g., "Helsinki-NLP/opus-mt-en-de"
        self.device = self.config.get("device", "cpu")
        self.model_manager = HFModelManager(cache_dir=self.cache_dir)
        self._translator: Optional[HFTranslator] = None

    def _ensure_translator(self):
        if self._translator:
            return
        if not self.model_name:
            raise RuntimeError("No Hugging Face model selected in the HuggingFaceEngine configuration.")
        # If a local snapshot exists, pass path else use model id
        model_path = self.model_name
        try:
            self._translator = HFTranslator(model_path, device=self.device, cache_dir=self.cache_dir)
        except Exception as e:
            raise RuntimeError(f"Failed to load Hugging Face model '{self.model_name}': {e}") from e

    def translate_entries(self, entries: List[dict], source_lang: str, target_lang: str, progress_callback=None):
        """Translate a list of entries (similar shape used by AITranslator)."""
        self._ensure_translator()
        items = [entry for entry in entries if not entry.get("obsolete")]
        texts = [entry.get("msgid", "") for entry in items]
        translated_texts = self._translator.translate(texts, batch_size=self.config.get("batch_size", 8))
        # Merge back by position (not by msgid) to handle duplicate source strings.
        result_entries = [dict(entry) for entry in entries]
        i = 0
        total = len(items)
        for idx, entry in enumerate(result_entries):
            if not entry.get("obsolete"):
                result_entries[idx]["msgstr"] = translated_texts[i] if i < len(translated_texts) else ""
                if i < len(translated_texts):
                    result_entries[idx]["fuzzy"] = False  # updated against the current source
                i += 1
                if progress_callback:
                    progress_callback(i, total)
        return result_entries, {"prompt_tokens": 0, "completion_tokens": 0}