import wx
import os
import json
from pathlib import Path
from format_handlers.compatibility import LegacyCompatibilityAdapter
from ..constants import PROJECT_FILE_EXT

def on_open_file(frame, event):
    wildcard = frame.format_manager.get_file_dialog_wildcard()
    project_wildcard = f"Project (*{PROJECT_FILE_EXT})|*{PROJECT_FILE_EXT}"
    full_wildcard = f"{project_wildcard}|{wildcard}"

    with wx.FileDialog(frame, "Open File", wildcard=full_wildcard, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            _, ext = os.path.splitext(path)
            try:
                if ext == PROJECT_FILE_EXT:
                    _load_project_file(frame, path)
                    frame.show_review_interface()
                else:
                    frame.po_file_path = path
                    frame.last_save_path = None  # fresh source → ask where to save first time
                    translation_units, handler = frame.format_manager.load_file(path)
                    frame.all_po_entries = LegacyCompatibilityAdapter.to_legacy_format(translation_units)
                    frame.file_type = handler.format_name if handler else 'unknown'
                    frame.show_translation_interface()
            except Exception as e:
                wx.MessageBox(f"Error loading file: {e}", "Error", wx.OK | wx.ICON_ERROR)

def on_open_project(frame, event):
    format_wildcard = frame.format_manager.get_file_dialog_wildcard()
    project_wildcard = f"Project (*{PROJECT_FILE_EXT})|*{PROJECT_FILE_EXT}"
    full_wildcard = f"{project_wildcard}|{format_wildcard}|All files (*.*)|*.*"
    with wx.FileDialog(frame, "Open Project", wildcard=full_wildcard, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            _, ext = os.path.splitext(path)
            try:
                if ext == PROJECT_FILE_EXT:
                    _load_project_file(frame, path)
                    frame.show_review_interface()
                else:
                    frame.po_file_path = path
                    frame.last_save_path = None  # fresh source → ask where to save first time
                    translation_units, handler = frame.format_manager.load_file(path)
                    frame.all_po_entries = LegacyCompatibilityAdapter.to_legacy_format(translation_units)
                    frame.file_type = handler.format_name if handler else 'unknown'
                    frame.show_translation_interface()
            except Exception as e:
                wx.MessageBox(f"Error loading project: {e}", "Error", wx.OK | wx.ICON_ERROR)

def on_save_changes(frame, event, batch_mode=False, save_as=False):
    """Save the finalized translation.

    The destination is remembered in ``frame.last_save_path`` after the first
    save, so subsequent saves write straight back to that file with no dialog
    and no modal confirmation (a status-bar message instead). Pass
    ``save_as=True`` (File → Save As…) to force the file dialog and pick a new
    destination.
    """
    if not batch_mode:
        frame.save_current_entry_changes()
    entries_to_save = frame.translated_po_entries
    if not frame.po_file_path:
        return

    if not batch_mode and frame.highest_reviewed_index < len(frame.translated_po_entries) - 1:
        msg = (f"You have reviewed up to entry {frame.highest_reviewed_index + 1} of {len(frame.translated_po_entries)}.\n\n"
               "How would you like to save?")
        with wx.MessageDialog(frame, msg, "Save Progress", wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION) as dlg:
            dlg.SetYesNoLabels("Save Reviewed Only", "Save All (Auto-approve)")
            res = dlg.ShowModal()
            if res == wx.ID_YES:
                entries_to_save = frame.translated_po_entries[:frame.highest_reviewed_index + 1]
            elif res == wx.ID_CANCEL:
                return

    # Reuse the remembered destination unless the user explicitly asked to
    # "Save As…". This is what stops the file dialog appearing on every save.
    remembered = getattr(frame, 'last_save_path', None)
    reuse = bool(remembered) and not save_as
    if reuse:
        output_path = remembered
    else:
        base, ext = os.path.splitext(frame.po_file_path)
        default_output = f"{base}_translated{ext}"
        wildcard = frame.format_manager.get_file_dialog_wildcard()
        with wx.FileDialog(frame, "Save Final Translation", defaultFile=default_output, wildcard=wildcard,
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            output_path = dlg.GetPath()

    try:
        translation_units = LegacyCompatibilityAdapter.from_legacy_format(entries_to_save)
        save_options = {'source_path': Path(frame.po_file_path)}
        frame.format_manager.save_file(translation_units, Path(output_path), **save_options)
        frame.last_save_path = output_path
        _update_translation_memory(frame, translation_units, silent=True)
        # Quiet confirmation for silent re-saves; a modal only for the first
        # save / explicit Save As so the user knows where it went.
        _notify_saved(frame, output_path, silent=reuse or batch_mode)
    except Exception as e:
        wx.MessageBox(f"Error saving file: {e}", "Error", wx.OK | wx.ICON_ERROR)


def _notify_saved(frame, output_path, silent=False):
    """Confirm a successful save. Silent saves use the status bar; otherwise a
    modal dialog tells the user the destination."""
    name = os.path.basename(output_path)
    try:
        frame.SetStatusText(f"Saved to {name}")
    except Exception:
        pass
    if not silent:
        wx.MessageBox(f"Saved to: {output_path}", "Success", wx.OK | wx.ICON_INFORMATION)

def on_save_project(frame, event):
    if not frame.translated_po_entries:
        wx.MessageBox("No project data to save.", "Info")
        return
    wildcard = f"Project File (*{PROJECT_FILE_EXT})|*{PROJECT_FILE_EXT}"
    with wx.FileDialog(frame, "Save Project As", wildcard=wildcard, style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
        if dlg.ShowModal() == wx.ID_OK:
            _save_project_file(frame, dlg.GetPath())

def _save_project_file(frame, path):
    frame.save_current_entry_changes()
    project_data = {
        "original_file": frame.po_file_path,
        "file_type": frame.file_type,
        "review_entries": frame.translated_po_entries,
        "current_index": frame.current_entry_index,
        "highest_reviewed_index": frame.highest_reviewed_index,
        "source_language": frame.source_language,
        "target_language": frame.target_language,
        "exclusion_rules": frame.exclusion_manager.to_json(), # Save exclusion rules
        "last_save_path": getattr(frame, 'last_save_path', None),
    }
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(project_data, f, indent=2)
        wx.MessageBox(f"Project saved to {path}", "Project Saved", wx.OK | wx.ICON_INFORMATION)
    except Exception as e:
        wx.MessageBox(f"Error saving project: {e}", "Error", wx.OK | wx.ICON_ERROR)

def _load_project_file(frame, path):
    with open(path, 'r', encoding='utf-8') as f:
        project_data = json.load(f)
    frame.po_file_path = project_data.get("original_file")
    frame.file_type = project_data.get("file_type")
    frame.translated_po_entries = project_data.get("review_entries", [])
    frame.current_entry_index = project_data.get("current_index", 0)
    frame.highest_reviewed_index = project_data.get("highest_reviewed_index", frame.current_entry_index)
    frame.source_language = project_data.get("source_language", "en") # Default to 'en' if not found
    frame.target_language = project_data.get("target_language", "es") # Default to 'es' if not found
    frame.last_save_path = project_data.get("last_save_path")  # remembered save destination

    # Load exclusion rules
    exclusion_rules_data = project_data.get("exclusion_rules", [])
    from exprules import ExclusionManager # Import here to avoid circular dependency if it's already imported elsewhere
    frame.exclusion_manager = ExclusionManager.from_json(exclusion_rules_data)

    frame.all_po_entries = frame.translated_po_entries

def on_load_ignore_list(frame, event):
    wildcard = "Text files (*.txt)|*.txt|All files (*.*)|*.*"
    with wx.FileDialog(frame, "Load Ignore List", wildcard=wildcard, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    frame.file_ignore_rules = [line.strip() for line in f if line.strip()]
                wx.MessageBox(f"Loaded {len(frame.file_ignore_rules)} ignore rules from {os.path.basename(path)}.", "Success", wx.OK | wx.ICON_INFORMATION)
                # Refresh the entry list only if the translation interface is active
                if hasattr(frame, 'translation_mode_radio'):
                    frame.on_filter_entries(None)
            except Exception as e:
                wx.MessageBox(f"Error loading ignore list: {e}", "Error", wx.OK | wx.ICON_ERROR)

def on_select_termbase(frame, event):
    """Pick which termbase / translation-memory file this project uses.

    Different jobs need different termbases - the same term is translated
    differently depending on the product. The choice is remembered in the
    config and the file is created on first save if it does not exist yet.
    """
    from translation_memory import TranslationMemory
    wildcard = "Termbase / TM (*.json)|*.json|All files (*.*)|*.*"
    current = getattr(frame.translation_memory, 'db_path', '')
    with wx.FileDialog(frame, "Select Termbase", defaultFile=os.path.basename(current or ''),
                       wildcard=wildcard, style=wx.FD_SAVE) as dlg:
        if dlg.ShowModal() != wx.ID_OK:
            return
        path = dlg.GetPath()
    try:
        frame.translation_memory = TranslationMemory(path)
    except Exception as e:
        wx.MessageBox(f"Could not load termbase: {e}", "Error", wx.OK | wx.ICON_ERROR)
        return
    frame.config['tm_path'] = path
    frame.save_config()
    count = len(frame.translation_memory.get_all_entries())
    wx.MessageBox(f"Termbase set to {os.path.basename(path)} ({count} entries).",
                  "Termbase", wx.OK | wx.ICON_INFORMATION)


def _update_translation_memory(frame, saved_entries, silent=False):
    # Use stored instance variables for source and target languages
    src_lang = frame.source_language
    tgt_lang = frame.target_language
    for unit in saved_entries:
        if unit.source and unit.target:
            frame.translation_memory.add_entry(unit.source, unit.target, src_lang, tgt_lang)
    if not silent:
        wx.MessageBox("Translation memory updated.", "Success", wx.OK | wx.ICON_INFORMATION)
