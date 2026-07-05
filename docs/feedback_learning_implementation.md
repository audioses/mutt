# Feedback Learning System Implementation

## Overview
This document provides the implementation details for the Feedback Learning System that will be used to capture and analyze the differences between AI-generated translations and human-edited versions.

## File: feedback_learning.py

```python
import json
import os
from datetime import datetime
from typing import List, Dict, Optional

class FeedbackLearningSystem:
    def __init__(self, db_path: str = "feedback_data.json"):
        """
        Initialize the Feedback Learning System.
        
        Args:
            db_path (str): Path to the feedback database file
        """
        self.db_path = db_path
        self.feedback_data = self._load_feedback()
    
    def _load_feedback(self) -> List[Dict]:
        """
        Load existing feedback data from the database file.
        
        Returns:
            List[Dict]: List of feedback entries
        """
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading feedback data: {e}")
                return []
        return []
    
    def _save_feedback(self):
        """
        Save feedback data to the database file.
        """
        try:
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(self.feedback_data, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving feedback data: {e}")
    
    def add_feedback_entry(self, source: str, ai_translation: str, human_translation: str,
                          source_lang: str, target_lang: str, model_info: Dict):
        """
        Add a new feedback entry to the database.
        
        Args:
            source (str): Original text to translate
            ai_translation (str): AI-generated translation
            human_translation (str): Human-edited translation
            source_lang (str): Source language code
            target_lang (str): Target language code
            model_info (Dict): Information about the model used
        """
        entry = {
            "source": source,
            "ai_translation": ai_translation,
            "human_translation": human_translation,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "model_used": model_info.get('model', ''),
            "provider": model_info.get('provider', ''),
        }
        
        self.feedback_data.append(entry)
        self._save_feedback()
    
    def get_all_feedback(self) -> List[Dict]:
        """
        Get all feedback entries.
        
        Returns:
            List[Dict]: List of all feedback entries
        """
        return self.feedback_data
    
    def get_feedback_for_language_pair(self, source_lang: str, target_lang: str) -> List[Dict]:
        """
        Get feedback entries for a specific language pair.
        
        Args:
            source_lang (str): Source language code
            target_lang (str): Target language code
            
        Returns:
            List[Dict]: List of feedback entries for the language pair
        """
        return [
            entry for entry in self.feedback_data
            if entry["source_lang"] == source_lang and entry["target_lang"] == target_lang
        ]
    
    def get_feedback_for_model(self, provider: str, model: str) -> List[Dict]:
        """
        Get feedback entries for a specific model.
        
        Args:
            provider (str): AI provider name
            model (str): Model name
            
        Returns:
            List[Dict]: List of feedback entries for the model
        """
        return [
            entry for entry in self.feedback_data
            if entry["provider"] == provider and entry["model_used"] == model
        ]
    
    def clear_feedback(self):
        """
        Clear all feedback data.
        """
        self.feedback_data = []
        self._save_feedback()
    
    def get_feedback_stats(self) -> Dict:
        """
        Get statistics about the feedback data.
        
        Returns:
            Dict: Statistics about the feedback data
        """
        if not self.feedback_data:
            return {
                "total_entries": 0,
                "language_pairs": [],
                "providers": [],
                "models": []
            }
        
        language_pairs = set()
        providers = set()
        models = set()
        
        for entry in self.feedback_data:
            language_pairs.add(f"{entry['source_lang']}-{entry['target_lang']}")
            providers.add(entry['provider'])
            models.add(entry['model_used'])
        
        return {
            "total_entries": len(self.feedback_data),
            "language_pairs": list(language_pairs),
            "providers": list(providers),
            "models": list(models)
        }
```

## Integration with Main Application

To integrate this feedback learning system with the main application, you'll need to make the following changes:

### 1. Import the Feedback Learning System

In `main.py`, add the import statement:

```python
from feedback_learning import FeedbackLearningSystem
```

### 2. Initialize the Feedback Learning System

In the `MainFrame` class constructor, add:

```python
self.feedback_learning = FeedbackLearningSystem()
self.ai_generated_translations = {}  # Store AI-generated translations by msgid
```

### 3. Capture AI-Generated Translations

Modify the `_run_translation` method to store AI output:

```python
def _run_translation(self, parent_frame, active_provider, settings, context):
    def p_cb(p, t): 
        wx.PostEvent(parent_frame, UpdateEvent(value=p, total=t))
    
    try:
        translator = AITranslator(
            active_provider, settings.get("api_key"), settings.get("api_model"),
            batch_size=self.config.get("batch_size", 50),
            temperature=self.config.get("temperature", 0.1),
            max_tokens=self.config.get("max_tokens", 4000),
            max_batch_tokens=self.config.get("max_batch_tokens", 16000)
        )

        # Gather surrounding context if enabled
        surrounding_context = []
        if self.config.get("enable_surrounding_context", False):
            current_batch_start_index = -1
            if self.po_entries and self.all_po_entries:
                # Find the index of the first entry in the current batch within all_po_entries
                try:
                    first_msgid_in_batch = self.po_entries[0]['msgid']
                    for idx, entry in enumerate(self.all_po_entries):
                        if entry.get('msgid') == first_msgid_in_batch:
                            current_batch_start_index = idx
                            break
                except IndexError:
                    pass # Batch might be empty

            if current_batch_start_index != -1:
                prev_size = self.config.get("context_previous_size", 2)
                next_size = self.config.get("context_next_size", 2)

                start_idx = max(0, current_batch_start_index - prev_size)
                end_idx = min(len(self.all_po_entries), current_batch_start_index + len(self.po_entries) + next_size)
                
                # Ensure we don't include the current batch in the surrounding context itself
                surrounding_context = self.all_po_entries[start_idx:current_batch_start_index] + \
                                      self.all_po_entries[current_batch_start_index + len(self.po_entries):end_idx]

        # Perform translation
        trans_data, usage = translator.translate_entries(
            self.po_entries,
            self.source_language,
            self.target_language,
            context,
            p_cb,
            surrounding_context=surrounding_context
        )
        
        # NEW: Store AI-generated translations
        self.ai_generated_translations = {}
        for entry in trans_data:
            entry_id = entry.get('msgid', '')  # Use msgid as identifier
            self.ai_generated_translations[entry_id] = entry.get('msgstr', '')
        
        wx.PostEvent(parent_frame, ResultEvent(source="translation", result=trans_data, usage=usage, error=None))
    except Exception as e:
        wx.PostEvent(parent_frame, ResultEvent(source="translation", error=e))
```

### 4. Save Feedback Data

Update the `_update_translation_memory` method to save feedback:

```python
def _update_translation_memory(self, saved_entries):
    # Use stored instance variables for source and target languages
    src_lang = self.source_language
    tgt_lang = self.target_language
    for entry in saved_entries:
        source = entry.get("msgid", "")
        target = entry.get("msgstr", "")
        if source and target:
            self.translation_memory.add_entry(source, target, src_lang, tgt_lang)
    
    # NEW: Save feedback data
    self._save_feedback_data(saved_entries)

def _save_feedback_data(self, saved_entries):
    """
    Compare AI translations with final translations and save feedback.
    """
    # Compare AI translations with final translations and save feedback
    for entry in saved_entries:
        msgid = entry.get('msgid', '')
        ai_translation = self.ai_generated_translations.get(msgid, '')
        human_translation = entry.get('msgstr', '')
        
        # Only save feedback if there's a difference and both translations exist
        if (ai_translation and human_translation and 
            ai_translation != human_translation and 
            ai_translation.strip() != human_translation.strip()):
            self.feedback_learning.add_feedback_entry(
                source=msgid,
                ai_translation=ai_translation,
                human_translation=human_translation,
                source_lang=self.source_language,
                target_lang=self.target_language,
                model_info={
                    'model': self.config.get("providers", {}).get(self.config.get("last_provider"), {}).get("api_model", ""),
                    'provider': self.config.get("last_provider", "")
                }
            )
```

## Future Enhancements

Once you've collected sufficient feedback data, you can implement these enhancements:

### 1. Pattern Analysis

```python
def analyze_modification_patterns(self) -> Dict:
    """
    Analyze common patterns in how humans modify AI translations.
    
    Returns:
        Dict: Analysis of modification patterns
    """
    # Implementation would analyze the differences between AI and human translations
    # to identify common modification types (e.g., formality changes, cultural adaptations)
    pass
```

### 2. Quality Scoring

```python
def calculate_translation_quality_score(self, source: str, translation: str) -> float:
    """
    Calculate a quality score for a translation based on feedback data.
    
    Args:
        source (str): Original text
        translation (str): Translation to score
        
    Returns:
        float: Quality score between 0 and 1
    """
    # Implementation would compare the translation to similar entries in feedback data
    pass
```

### 3. Model Performance Analysis

```python
def analyze_model_performance(self) -> Dict:
    """
    Analyze which models perform best based on feedback data.
    
    Returns:
        Dict: Performance analysis by model
    """
    # Implementation would calculate metrics like:
    # - Average edit distance between AI and human translations
    # - Percentage of AI translations accepted without changes
    # - User preference by model
    pass
```

This implementation provides a solid foundation for the feedback learning system that can be extended with more sophisticated analysis features as more data is collected.