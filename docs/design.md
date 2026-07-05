# Technical Design: MUTT Feature Enhancement (Revised)

This document outlines the revised technical design for three new features in the MUTT application, incorporating feedback to leverage existing systems.

1.  **Etymology Tool**
2.  **Ignore Rules by File**
3.  **Contextual AI Prompts (Previous & Next)**
4.  **Translation Memory Integration**

---

## 1. Etymology Tool

This feature will be integrated into the existing **Translator's Toolbox** using the AI prompt system, instead of a new dialog and external API.

### 1.1. System Design

*   A new system prompt will be created specifically for etymology lookups.
*   The tool will leverage the existing `AITranslator` and the tool execution flow in `MainFrame`.

### 1.2. File Modifications

*   **`main.py`**:
    *   In the `DEFAULT_PROMPTS` list, a new prompt object will be added:
        ```python
        {"name": "Tool: Get Etymology", "prompt": "Provide a concise etymology for the following word: {source_text}", "system": True}
        ```
    *   The `show_review_interface` method will automatically pick up this new tool and add it to the `chat_mode_radio` choices. No other UI changes are needed. The existing `on_tool_execute` and `_run_tool` methods will handle the logic. When the user selects a word and executes the tool, the `source_text` in the prompt will be replaced by the selected word.

### 1.3. Workflow

1.  The user highlights a word in the source or target text control in the review interface.
2.  The user selects "Get Etymology" from the "Tool Mode" radio buttons in the Translator's Toolbox.
3.  The user clicks "Execute Tool".
4.  The existing `_run_tool` method in `MainFrame` is called, which uses the new system prompt to ask the AI for the etymology.
5.  The result is displayed in the `tool_results_list`, just like other tool results.

---

## 2. Ignore Rules by File

This feature will extend the existing exclusion rule system by allowing users to load a list of ignore terms from a text file.

### 2.1. System Design

*   The application already has regex and sectional exclusion rules. This will add a third type: a simple list of strings loaded from a file.
*   The ignore rules from the file will be stored in a new list within the `MainFrame` instance.

### 2.2. User Interface

*   **Menu Item:** A new menu item, "Load Ignore List...", will be added to the `File` menu in `create_menu_bar`.

### 2.3. File Modifications

*   **`main.py`**:
    *   In `MainFrame.__init__`, add `self.file_ignore_rules = []`.
    *   In `create_menu_bar`, add the new menu item and bind it to a new handler, `on_load_ignore_list`.
    *   **`on_load_ignore_list(self, event)`**: This new method will:
        *   Open a `wx.FileDialog` to select a `.txt` file.
        *   Read the file line by line, stripping whitespace, and populate `self.file_ignore_rules`.
        *   Call `self.on_filter_entries(None)` to refresh the entry list.
    *   In `on_filter_entries`, an additional filter will be added to the logic. After applying the existing regex and sectional rules, it will further filter the list:
        ```python
        if self.file_ignore_rules:
            filtered_entries = [
                entry for entry in filtered_entries 
                if entry.get('msgid', '').strip() not in self.file_ignore_rules
            ]
        ```

---

## 3. Contextual AI Prompts (Previous & Next)

This feature will be revised to send both previous and *next* untranslated entries from the source file to provide the AI with surrounding context.

### 3.1. System Design (Final Revision)

*   **Correct Context Source:** The context will be drawn from `self.all_po_entries` (the complete, original source file data) to ensure the surrounding entries are always adjacent, regardless of their translation status. This corrects the flaw of only looking at untranslated entries.
*   **Configuration:** The user can enable/disable this feature and control the number of previous and next entries to send.
    *   A checkbox "Enable Contextual Prompts" will be added.
    *   Spin controls for "Previous Context Size" and "Next Context Size" will control the length.

### 3.2. User Interface

*   **`APISetupDialog`**:
    *   A `wx.CheckBox` labeled "Enable Surrounding Context" will be added to the "Advanced Settings" tab.
    *   Two `wx.SpinCtrl` widgets: "Previous Context Size (entries)" and "Next Context Size (entries)". These will be enabled/disabled based on the checkbox.

### 3.3. File Modifications

*   **`ui_dialogs.py`**:
    *   In `APISetupDialog.setup_advanced_tab`, add the new `CheckBox` and `SpinCtrl` widgets.
    *   In `APISetupDialog.on_ok`, save these values (`enable_surrounding_context`, `context_previous_size`, `context_next_size`) to `self.config`.
*   **`main.py`**:
    *   In `_run_translation`, if the feature is enabled, it will find the index of the first item of the current batch within `self.all_po_entries`. It will then slice `N` entries before and `M` entries after that index from `self.all_po_entries` to create the context.
    *   This context list (containing full entry dictionaries) will be passed to `translator.translate_entries`.
*   **`ai_translator.py`**:
    *   `translate_entries` will accept a `surrounding_context` argument.
    *   `_build_user_prompt` will be updated. For previous entries, it will include both source and target (if available) to show the AI translation examples. For next entries, it will only include the source.
        ```
        ...
        For context, here are the entries immediately preceding the ones to translate:
        - Source: "Hello" -> Target: "Hola"
        - Source: "How are you?" -> Target: "¿Cómo estás?"

        And here are the source texts of the entries immediately following:
        - Source: "This is the next sentence."
        - Source: "And another one."

        Now, translate the following JSON array...
        ```
---

## 4. Translation Memory Integration

This new step ensures that all successfully saved translations are added to the application's long-term translation memory.

### 4.1. System Design

*   The existing `TranslationMemory` class will be used.
*   An instance of `TranslationMemory` will be created in `MainFrame`.
*   After any "save" operation that writes final translations to a file, the saved pairs will be added to the memory.

### 4.2. File Modifications

*   **`main.py`**:
    *   Import `TranslationMemory` at the top.
    *   In `MainFrame.__init__`, add `self.translation_memory = TranslationMemory()`.
    *   Create a new helper method: `_update_translation_memory(self, saved_entries)`. This method will:
        *   Get the source and target languages from the UI controls.
        *   Iterate through `saved_entries`.
        *   For each entry, call `self.translation_memory.add_entry(source, target, src_lang, tgt_lang)`.
    *   In `on_save_changes`, after a successful file save operation (inside the `try` block), call `self._update_translation_memory(entries_to_save)`.