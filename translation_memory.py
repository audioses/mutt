import json
import os
from typing import List, Dict, Optional

class TranslationMemory:
    def __init__(self, db_path: str = "translation_memory.json"):
        self.db_path = db_path
        self.memory = self._load_memory()

    def _load_memory(self) -> List[Dict]:
        if os.path.exists(self.db_path):
            with open(self.db_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def _save_memory(self):
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(self.memory, f, indent=4, ensure_ascii=False)

    def add_entry(self, source: str, target: str, source_lang: str, target_lang: str):
        entry = {
            "source": source,
            "target": target,
            "source_lang": source_lang,
            "target_lang": target_lang
        }
        self.memory.append(entry)
        self._save_memory()

    def find_entry(self, source: str, source_lang: str, target_lang: str) -> Optional[str]:
        for entry in self.memory:
            if entry["source"] == source and \
               entry["source_lang"] == source_lang and \
               entry["target_lang"] == target_lang:
                return entry["target"]
        return None

    def get_all_entries(self) -> List[Dict]:
        return self.memory

    def clear_memory(self):
        self.memory = []
        self._save_memory()

    def delete_entry(self, source: str, target: str, source_lang: str, target_lang: str) -> bool:
        initial_len = len(self.memory)
        self.memory = [
            entry for entry in self.memory
            if not (entry["source"] == source and
                    entry["target"] == target and
                    entry["source_lang"] == source_lang and
                    entry["target_lang"] == target_lang)
        ]
        if len(self.memory) < initial_len:
            self._save_memory()
            return True
        return False