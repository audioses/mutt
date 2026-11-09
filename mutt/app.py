#!/usr/bin/env python3
"""
MUTT - Professional Translation Suite
One tool, all languages, unlimited possibilities
"""
import os
import sys
import wx
import wx.lib.newevent
import json
import re
import threading

import logging
import traceback

from translation_memory import TranslationMemory
from mutt.ui.dialogs.api_setup import APISetupDialog
from mutt.ui.dialogs.exclusion import ExclusionRulesManagerDialog
from mutt.ui.dialogs.prompt import PromptManagerDialog
from mutt.ui.dialogs.jump import JumpDialog
from mutt.ui.dialogs.search import SearchDialog
from exprules import ExclusionManager
from format_handlers.base.manager import FormatManager

from mutt.constants import *
from mutt.api_helper import APIHelper
from mutt.secure_keys import (
    PLACEHOLDER_PREFIX as KEYRING_PLACEHOLDER_PREFIX,
    dehydrate_config_for_disk,
    hydrate_config,
)
from mutt.ui.menu import create_menu_bar
from mutt.ui.utils import on_ctrl_backspace
from mutt.ui.translation_panel import create_translation_panel
from mutt.ui.dynamic_panel import create_dynamic_panel
import yaml
from pathlib import Path
# Argos engine helpers are now lazily imported in ai_translator.py
from mutt.ui.review_panel import create_review_panel
from mutt.logic.translation import run_translation_thread
from mutt.logic.tool_logic import run_tool_thread
from mutt.logic.mode_loader import instantiate_mode
from mutt.logic.entry_filter import is_entry_untranslated, select_entries_for_translation
from mutt.logic.plurals import (
    plural_forms, form_label, source_for_form, target_for_form, set_target_for_form,
)
from mutt.logic.notes import format_entry_notes
from mutt.logic.file_operations import (
    on_open_file, on_open_project, on_load_ignore_list, on_save_changes,
    on_save_project, _save_project_file, _load_project_file,
    _update_translation_memory, on_select_termbase
)
from mutt.logic.autosave import AutosaveManager, RecoverableSession


class MainFrame(wx.Frame):
    def __init__(self, parent, title):
        super(MainFrame, self).__init__(parent, title=title, size=(800, 850))

        # Setup logging first
        self.setup_logging()
        self.logger.info("=== MUTT Starting ===")

        self.panel = wx.Panel(self)
        self.config = self.load_config()
        self._migrate_config()
        self.format_manager = FormatManager()
        self.format_manager.registry.auto_discover()
        self.po_file_path = None
        self.file_type = None # This will now be managed by FormatManager
        # Remembered destination for "Save Final Translation" so repeated saves
        # don't re-prompt with a file dialog every time. Reset on opening a new
        # source file; persisted in project files.
        self.last_save_path = None
        # Cooperative cancellation flag for the background translation loop.
        self.cancel_event = threading.Event()
        self.all_po_entries = []
        self.po_entries = []
        self.exclusion_manager = ExclusionManager()
        self.translated_po_entries = []
        self.current_entry_index = 0
        self.highest_reviewed_index = -1
        self.search_dialog = None
        # Which plural form the review panel is currently editing (None for
        # entries without a msgid_plural).
        self.current_plural_form = None
        self.file_ignore_rules = [] # NEW: for file-based ignore rules
        # Active termbase / TM. Selectable per project via Settings menu.
        self.translation_memory = TranslationMemory(
            self.config.get("tm_path") or "translation_memory.json"
        )
        self.source_language = "en" # Initialize source language
        self.target_language = "es" # Initialize target language

        # Setup global exception handler
        sys.excepthook = self.handle_exception

        # Crash-safe autosave. Snapshot callback serialises the same
        # shape that `_save_project_file` writes so recovery can round-trip
        # through the existing project-load code path.
        self.autosave_manager = AutosaveManager(snapshot_fn=self._autosave_snapshot)
        self.autosave_manager.start()

        create_menu_bar(self)
        self.create_widgets()
        self.Centre()
        self.Show()

        self.Bind(EVT_UPDATE, self.on_update_progress)
        self.Bind(EVT_RESULT, self.on_result)
        self.Bind(wx.EVT_CLOSE, self.on_close_frame)
        self.Bind(wx.EVT_CHAR_HOOK, on_ctrl_backspace)

        wx.CallAfter(self._offer_autosave_recovery)

    def setup_logging(self):
        """Setup comprehensive logging for debugging crashes."""
        self.logger = logging.getLogger('MUTT')
        self.logger.setLevel(logging.DEBUG)

        # Create file handler (force UTF-8 to avoid Windows encoding errors)
        handler = logging.FileHandler('mutt_debug.log', mode='w', encoding='utf-8')
        handler.setLevel(logging.DEBUG)

        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s')
        handler.setFormatter(formatter)

        self.logger.addHandler(handler)

        # Also log to console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.ERROR)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """Global exception handler to catch all unhandled exceptions."""
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        self.logger.critical(f"UNHANDLED EXCEPTION: {error_msg}")

        # Flush autosave BEFORE showing the dialog so the user's work is
        # preserved even if the dialog itself fails to render. Do a
        # synchronous one-shot write rather than stop()ing the manager so
        # the app can keep autosaving if wx recovers after a non-fatal
        # exception.
        try:
            mgr = getattr(self, "autosave_manager", None)
            if mgr is not None:
                snapshot = self._autosave_snapshot()
                if snapshot is not None:
                    mgr._write_once(blocking=True, preset_snapshot=snapshot)
        except Exception:
            self.logger.error("Autosave flush from excepthook failed", exc_info=True)

        # Show error dialog if possible
        try:
            wx.MessageBox(f"Critical error occurred. Check mutt_debug.log for details.\n\nError: {exc_value}",
                         "Application Error", wx.OK | wx.ICON_ERROR)
        except Exception:
            pass  # If we can't show the dialog, at least we logged it

    def load_config(self):
        if not os.path.exists(CONFIG_FILE): return {}
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
        # Replace any "keyring:<provider>" placeholders with the real keys
        # fetched from the OS keyring. cfg is mutated in place.
        return hydrate_config(cfg)

    def save_config(self):
        # Move any plaintext api_key values into the OS keyring and
        # replace them with placeholders before writing the JSON to disk.
        on_disk = dehydrate_config_for_disk(self.config)
        with open(CONFIG_FILE, "w") as f: json.dump(on_disk, f, indent=4)

    def _has_plaintext_api_keys(self) -> bool:
        for settings in (self.config.get("providers") or {}).values():
            if not isinstance(settings, dict):
                continue
            val = settings.get("api_key", "")
            if val and not str(val).startswith(KEYRING_PLACEHOLDER_PREFIX):
                return True
        return False

    def _migrate_config(self):
        # One-shot: if config.json still holds plaintext keys, force a save
        # so they are migrated into the OS keyring and replaced by placeholders.
        if self._has_plaintext_api_keys():
            self.save_config()

        if "prompts" not in self.config:
            self.config["prompts"] = DEFAULT_PROMPTS
            self.save_config()
            return
        if self.config["prompts"] and isinstance(self.config["prompts"][0], str):
            migrated_prompts = [{"name": f"Custom Prompt {i+1}", "prompt": p_str, "system": False} for i, p_str in enumerate(self.config["prompts"])]
            existing_names = {p["name"] for p in migrated_prompts}
            for default_prompt in DEFAULT_PROMPTS:
                if default_prompt["name"] not in existing_names:
                    migrated_prompts.append(default_prompt)
            self.config["prompts"] = migrated_prompts
            self.save_config()
            wx.MessageBox("Prompts have been updated to a new format.", "Configuration Updated", wx.OK | wx.ICON_INFORMATION)

        existing_names = {p["name"] for p in self.config["prompts"]}
        new_defaults_added = False
        for default_prompt in DEFAULT_PROMPTS:
            if default_prompt["name"] not in existing_names:
                self.config["prompts"].append(default_prompt)
                new_defaults_added = True

        if new_defaults_added:
            self.save_config()

    def create_widgets(self):
        self.panel.DestroyChildren()
        if not self.config.get("providers"):
            wx.CallAfter(self.show_api_selection_dialog)
        else:
            self.show_main_app_content()
        self.panel.Layout()

        accel_tbl = wx.AcceleratorTable([
            (wx.ACCEL_ALT, ord('N'), ID_NEXT_ENTRY),
            (wx.ACCEL_ALT, ord('P'), ID_PREVIOUS_ENTRY),
            (wx.ACCEL_ALT, wx.WXK_UP, ID_PREVIOUS_ENTRY),
            (wx.ACCEL_ALT, wx.WXK_DOWN, ID_NEXT_ENTRY),
            (wx.ACCEL_ALT, wx.WXK_LEFT, ID_FOCUS_SOURCE),
            (wx.ACCEL_ALT, wx.WXK_RIGHT, ID_FOCUS_TARGET),
            (wx.ACCEL_CTRL, ord('F'), ID_SEARCH),
            (wx.ACCEL_ALT, ord('J'), ID_JUMP),
            (wx.ACCEL_ALT, ord('C'), ID_FOCUS_NOTES),
            (wx.ACCEL_ALT, ord('U'), ID_FOCUS_PLURAL),
        ])
        self.SetAcceleratorTable(accel_tbl)
        self.Bind(wx.EVT_MENU, self.on_next_entry, id=ID_NEXT_ENTRY)
        self.Bind(wx.EVT_MENU, self.on_prev_entry, id=ID_PREVIOUS_ENTRY)
        self.Bind(wx.EVT_MENU, self.on_focus_source, id=ID_FOCUS_SOURCE)
        self.Bind(wx.EVT_MENU, self.on_focus_target, id=ID_FOCUS_TARGET)
        self.Bind(wx.EVT_MENU, self.on_focus_notes, id=ID_FOCUS_NOTES)
        self.Bind(wx.EVT_MENU, self.on_focus_plural, id=ID_FOCUS_PLURAL)
        self.Bind(wx.EVT_MENU, self.on_show_search_dialog, id=ID_SEARCH)
        self.Bind(wx.EVT_MENU, self.on_show_jump_dialog, id=ID_JUMP)

    def on_focus_source(self, event):
        if hasattr(self, 'src_text_ctrl'): self.src_text_ctrl.SetFocus()
    def on_focus_target(self, event):
        if hasattr(self, 'tgt_text_ctrl'): self.tgt_text_ctrl.SetFocus()
    def on_focus_notes(self, event):
        if hasattr(self, 'notes_text_ctrl'): self.notes_text_ctrl.SetFocus()
    def on_focus_plural(self, event):
        ctrl = getattr(self, 'plural_choice', None)
        if ctrl and ctrl.IsShown(): ctrl.SetFocus()

    def on_plural_form_change(self, event):
        """Switch which msgstr[n] the target box edits, keeping the edit made
        to the form we are leaving."""
        try:
            self.save_current_entry_changes()
            forms = plural_forms(self.translated_po_entries[self.current_entry_index])
            selection = self.plural_choice.GetSelection()
            if 0 <= selection < len(forms):
                self.current_plural_form = forms[selection]
            self.display_current_entry()
        except Exception as e:
            self.logger.error(f"Exception in on_plural_form_change: {e}", exc_info=True)

    def on_show_search_dialog(self, event):
        if not self.translated_po_entries: return
        if self.search_dialog: self.search_dialog.Raise(); return
        self.search_dialog = SearchDialog(self); self.search_dialog.Show()

    def on_show_jump_dialog(self, event):
        if not self.translated_po_entries: return
        with JumpDialog(self, len(self.translated_po_entries)) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                target_index = dlg.get_value() - 1
                if 0 <= target_index < len(self.translated_po_entries):
                    self.save_current_entry_changes()
                    self.current_entry_index = target_index
                    self.display_current_entry()

    def find_entry(self, term, scope, forward=True):
        if not term: return
        term = term.lower()
        start_index = self.current_entry_index + (1 if forward else -1)
        indices = list(range(len(self.translated_po_entries)))
        search_order = (indices[start_index:] + indices[:start_index]) if forward else (indices[:start_index+1][::-1] + indices[start_index+1:][::-1])
        for i in search_order:
            entry = self.translated_po_entries[i]
            # Plural entries keep their translations in msgstr[n], so search
            # those too or plural strings become unfindable by target text.
            source_text = " ".join([entry.get("msgid", ""), entry.get("source_plural", "") or ""]).lower()
            target_text = " ".join(
                [entry.get("msgstr", "") or ""] + [str(v) for v in (entry.get("target_plurals") or {}).values()]
            ).lower()
            match = False
            if scope == 0 and term in source_text: match = True
            elif scope == 1 and term in target_text: match = True
            elif scope == 2 and (term in source_text or term in target_text): match = True
            if match:
                self.save_current_entry_changes(); self.current_entry_index = i; self.display_current_entry(); return
        wx.MessageBox(f"'{term}' not found.", "Search Complete", wx.OK | wx.ICON_INFORMATION)

    def show_api_selection_dialog(self):
        self.logger.debug("show_api_selection_dialog called.")
        with APISetupDialog(self, self.config, APIHelper) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.logger.debug("API Setup Dialog closed with OK. Saving config.")
                self.save_config()
                wx.MessageBox("API settings saved.", "Success")
                self.logger.debug("Calling _recreate_ui_after_settings_change after API settings saved.")
                self._recreate_ui_after_settings_change()
                self.logger.debug("Returned from _recreate_ui_after_settings_change.")
            elif not self.config.get("providers"):
                self.logger.debug("No providers configured. Closing application.")
                self.Close()
            else:
                self.logger.debug("API Setup Dialog cancelled or failed, but providers exist.")

    def on_api_settings(self, event):
        self.logger.debug("on_api_settings menu item clicked.")
        self.show_api_selection_dialog()

    def _recreate_ui_after_settings_change(self):
        self.logger.debug("_recreate_ui_after_settings_change called.")
        self.panel.DestroyChildren()
        self.panel.SetSizer(wx.BoxSizer(wx.VERTICAL)) # Reset sizer

        # Determine which interface to show based on application state
        if self.translated_po_entries: # If a file has been translated, show review interface
            self.logger.debug("File translated, showing review interface.")
            self.show_review_interface()
        elif self.po_file_path: # If a file is open but not translated, show translation interface
            self.logger.debug("File open, showing translation interface.")
            self.show_translation_interface()
        else: # Otherwise, show the main app content (welcome screen)
            self.logger.debug("No file open, showing main app content.")
            self.show_main_app_content()
        
        self.panel.Layout()
        self.panel.Refresh()
        self.logger.debug("_recreate_ui_after_settings_change completed.")

    def on_manage_prompts(self, event):
        self.logger.debug("on_manage_prompts called.")
        with PromptManagerDialog(self, self.config.get("prompts", [])) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.config["prompts"] = dlg.get_prompts()
                self.save_config()
                if hasattr(self, 'prompt_combo'):
                    self.logger.debug("Prompt combo exists, calling show_translation_interface.")
                    self.show_translation_interface()
                wx.MessageBox("Prompts updated.", "Success")
                self.logger.debug("Prompts updated successfully.")

    def on_manage_exclusion_rules(self, event):
        self.logger.debug("on_manage_exclusion_rules called.")
        if not self.all_po_entries:
            wx.MessageBox("Please open a file first to manage exclusion rules.", "Info", wx.OK | wx.ICON_INFORMATION)
            self.logger.info("Cannot manage exclusion rules: no file open.")
            return
        with ExclusionRulesManagerDialog(self, self.exclusion_manager, self.all_po_entries) as dlg:
            dlg.ShowModal()
        self.on_filter_entries() # Re-apply filters after managing rules
        self.logger.debug("Exclusion rules managed and filters re-applied.")

    def show_main_app_content(self):
        self.logger.debug("show_main_app_content called.")
        self.panel.DestroyChildren()
        provider = self.config.get('last_provider', 'N/A')
        model = self.config.get("providers", {}).get(provider, {}).get("api_model", "N/A")
        status_text = (f"Welcome!\n\nProvider: {provider}\nModel: {model}\n\nOpen a file to begin.")
        wx.StaticText(self.panel, label=status_text, pos=(20, 20))
        self.logger.debug("Calling panel.Layout() in show_main_app_content.")
        self.panel.Layout()
        self.logger.debug("show_main_app_content completed.")

    def on_exit(self, event):
        self.logger.debug("on_exit called. Closing application.")
        self.Close(True)

    def on_open_file(self, event):
        self.logger.debug("on_open_file called.")
        on_open_file(self, event)

    def on_open_project(self, event):
        on_open_project(self, event)

    def _begin_translation_run(self, active_provider, settings, context, title="Translating..."):
        """Reset cancellation state, show an abortable progress dialog, and
        start the background translation thread.

        The progress dialog is created with ``wx.PD_CAN_ABORT`` so the user can
        stop a long run. Clicking Cancel sets ``self.cancel_event`` (see
        ``on_update_progress``); the worker polls it between batches and returns
        whatever it has already translated."""
        self.cancel_event = threading.Event()
        self.progress_dialog = wx.ProgressDialog(
            title, "Starting...",
            maximum=max(1, len(self.po_entries)),
            parent=self,
            style=(wx.PD_APP_MODAL | wx.PD_CAN_ABORT | wx.PD_AUTO_HIDE
                   | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME),
        )
        self.Disable()
        # Batches only report every few dozen entries, and the dialog's
        # elapsed/remaining clock only advances when it is Updated — so tick it
        # ourselves once a second, otherwise it sits at 0 for whole minutes.
        self._progress_value = 0
        self._progress_msg = "Starting..."
        if not hasattr(self, '_progress_timer'):
            self._progress_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._on_progress_tick, self._progress_timer)
        self._progress_timer.Start(1000)
        threading.Thread(
            target=run_translation_thread,
            args=(self, active_provider, settings, context),
            daemon=True,
        ).start()
        self.progress_dialog.Show()

    def on_translate(self, event):
        if not self.po_entries: wx.MessageBox("No entries to translate.", "Info"); return

        # Get selected translation method
        method_index = self.translation_method_radio.GetSelection()
        method_name = self.translation_method_radio.GetStringSelection()

        if method_index == 1:  # Human Translation
            # Skip translation and go directly to review interface
            self.translated_po_entries = self.po_entries.copy()
            self.current_entry_index = 0
            self.highest_reviewed_index = -1
            self.show_review_interface()
            wx.MessageBox("Human translation mode selected. You can now manually edit each entry.", "Info", wx.OK | wx.ICON_INFORMATION)
            return

        elif method_index == 2:  # Argos Translator
            # Use the Argos Translate provider for offline translation.
            context = self.prompt_combo.GetValue().strip() if hasattr(self, 'prompt_combo') else ""
            if context:
                prompt_names = [p["name"] for p in self.config.get("prompts", [])]
                if context not in prompt_names:
                    self.config["prompts"].append({"name": context, "prompt": context, "system": False})
                    self.save_config()
            
            # Save the selected method for persistence
            self.config['last_translation_method'] = method_name
            self.save_config()

            active_provider = "Argos Translate"
            settings = self.config.get("providers", {}).get(active_provider, {})
            self._begin_translation_run(active_provider, settings, context, "Translating (Argos)...")
            return

        elif method_index == 3:  # HuggingFace Neural Translation
            # Use the HuggingFace provider for local transformer-based translation
            context = self.prompt_combo.GetValue().strip() if hasattr(self, 'prompt_combo') else ""
            if context:
                prompt_names = [p["name"] for p in self.config.get("prompts", [])]
                if context not in prompt_names:
                    self.config["prompts"].append({"name": context, "prompt": context, "system": False})
                    self.save_config()
            
            # Save the selected method for persistence
            self.config['last_translation_method'] = method_name
            self.save_config()

            active_provider = "HuggingFace"
            settings = self.config.get("providers", {}).get(active_provider, {})

            # Basic validation: ensure a model is selected
            if not settings.get("api_model"):
                wx.MessageBox("No Hugging Face model selected. Configure your Hugging Face model in API Setup -> Manage Hugging Face Models.", "Error", wx.OK | wx.ICON_ERROR)
                return

            self._begin_translation_run(active_provider, settings, context, "Translating (HuggingFace)...")
            return

        # LLM Translation (index 0)
        context = self.prompt_combo.GetValue().strip()
        if context:
            prompt_names = [p["name"] for p in self.config.get("prompts", [])]
            if context not in prompt_names: self.config["prompts"].append({"name": context, "prompt": context, "system": False}); self.save_config()
        
        # Save the selected method for persistence
        self.config['last_translation_method'] = method_name
        self.save_config()

        active_provider = self.config.get("last_provider"); settings = self.config.get("providers", {}).get(active_provider, {})
        if not settings.get("api_model"): wx.MessageBox("API not configured.", "Error"); return
        self._begin_translation_run(active_provider, settings, context, "Translating...")

    def on_update_progress(self, event):
        self._progress_value = event.value
        self._progress_msg = f"Translated {event.value} of {event.total}..."
        self._refresh_progress()

    def _on_progress_tick(self, event):
        self._refresh_progress()

    def _refresh_progress(self):
        if not getattr(self, 'progress_dialog', None):
            return
        if self.cancel_event.is_set():
            # Already cancelling — keep the dialog responsive but don't fight
            # the user's choice by resetting the message on every tick.
            self.progress_dialog.Pulse("Cancelling… finishing the current batch.")
            return
        result = self.progress_dialog.Update(self._progress_value, self._progress_msg)
        # With PD_CAN_ABORT, Update returns (continue, skip); older builds may
        # return just a bool. Normalise both shapes.
        cont = result[0] if isinstance(result, tuple) else result
        if not cont:
            self.cancel_event.set()
            self.progress_dialog.Pulse("Cancelling… finishing the current batch.")

    def on_result(self, event):
        self.logger.info(f"on_result called with source: {getattr(event, 'source', 'unknown')}")

        # Always re-enable the main window, even if there's an error.
        self.Enable()

        try:
            # Log progress dialog state
            has_dialog = hasattr(self, 'progress_dialog')
            dialog_exists = has_dialog and self.progress_dialog is not None
            self.logger.debug(f"Progress dialog state - has_attr: {has_dialog}, exists: {dialog_exists}")

            timer = getattr(self, '_progress_timer', None)
            if timer:
                timer.Stop()

            if has_dialog and self.progress_dialog:
                self.logger.debug("Destroying progress dialog")
                self.progress_dialog.Destroy()
                delattr(self, 'progress_dialog')
                self.logger.debug("Progress dialog destroyed successfully")

            source = getattr(event, 'source', 'unknown')
            error = getattr(event, 'error', None)

            self.logger.debug(f"Event source: {source}, has_error: {error is not None}")

            if error:
                # Special handling for Argos package-missing interactive install flow.
                try:
                    from mutt.engines import argos_engine as current_argos_engine
                except Exception:
                    current_argos_engine = None

                argos_missing_err_type = getattr(current_argos_engine, "ArgosPackageMissingError", None) if current_argos_engine else None
                if argos_missing_err_type is not None and isinstance(error, argos_missing_err_type):
                    pkg = getattr(error, "suggested_package", None)
                    from_code = getattr(error, "from_code", None)
                    to_code = getattr(error, "to_code", None)

                    try:
                        
                        # Use the specific message from the error object for better user feedback
                        install_msg = f"{error}\n\nDo you want to try to install the required package now?"
                        if wx.MessageBox(install_msg, "Argos Package Required", wx.YES_NO | wx.ICON_QUESTION) == wx.YES:
                            if not pkg:
                                # This handles cases where a pivot language is missing, or the direct package isn't in the index.
                                wx.MessageBox("No direct package could be found automatically. Opening the Argos Package Manager for you to find a suitable package (e.g., a pivot language like English).", "Manual Installation Needed", wx.OK | wx.ICON_INFORMATION)
                                try:
                                    from mutt.ui.dialogs.argos import ArgosModelDialog
                                    with ArgosModelDialog(self) as dlg:
                                        dlg.ShowModal()
                                except Exception:
                                    wx.MessageBox("Could not open Argos Package Manager.", "Error", wx.OK | wx.ICON_ERROR)
                                return
                            # Create a modal progress dialog on the main thread before starting background work
                            install_progress = wx.ProgressDialog(
                                "Installing Argos Package",
                                f"Downloading {getattr(pkg,'name', str(pkg))}...",
                                maximum=100,
                                parent=self,
                                style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE
                            )
                            # Disable interaction
                            try:
                                self.translate_btn.Disable()
                            except Exception:
                                pass
                            def install_worker():
                                try:
                                    self.logger.info(f"Argos install worker started for {from_code}->{to_code}, pkg={getattr(pkg,'name',pkg)}")
                                    # Perform download & install (blocking) into app-local 'argos_models' directory
                                    try:
                                        target_dir = os.path.join(os.getcwd(), "argos_models")
                                        installed_path = current_argos_engine.download_and_install_package(pkg, target_dir=target_dir)
                                        self.logger.info(f"Argos package downloaded and installed at {installed_path}")
                                    except Exception as ie_inner:
                                        # Prefer Argos-specific error type when available for clearer logs and UI text
                                        ArgosErrType = getattr(current_argos_engine, "ArgosError", Exception) if current_argos_engine else Exception
                                        if isinstance(ie_inner, ArgosErrType):
                                            self.logger.exception("Argos-specific install error occurred")
                                        else:
                                            self.logger.exception("Unexpected error during Argos install")
                                        # Re-raise so outer handler shows failure UI via on_fail
                                        raise
                                    # Ensure UI updates are done on main thread
                                    def on_success():
                                        try:
                                            if install_progress and not getattr(install_progress, 'Destroyed', lambda: False)():
                                                try:
                                                    install_progress.Destroy()
                                                except Exception:
                                                    pass
                                        except Exception:
                                            pass
                                        wx.MessageBox(f"Installed package for {from_code} → {to_code}. Restarting translation.", "Installed", wx.OK | wx.ICON_INFORMATION)
                                        # Restart the translation using same provider/settings/context
                                        active_provider = "Argos Translate"
                                        settings = self.config.get("providers", {}).get(active_provider, {})
                                        context = self.prompt_combo.GetValue().strip() if hasattr(self, 'prompt_combo') else ""
                                        # Create and show the translation progress dialog on main thread
                                        try:
                                            self._begin_translation_run(active_provider, settings, context, "Translating (Argos)...")
                                        except Exception as ui_e:
                                            self.logger.exception("Failed to start translation UI after install")
                                            wx.MessageBox(f"Failed to start translation UI: {ui_e}", "Error", wx.OK | wx.ICON_ERROR)
                                    wx.CallAfter(on_success)
                                except Exception as ie:
                                    self.logger.exception("Argos install failed")
                                    install_error = ie  # capture for closure (except-as is cleared after block)
                                    def on_fail(err=install_error):
                                        try:
                                            if install_progress and not getattr(install_progress, 'Destroyed', lambda: False)():
                                                try:
                                                    install_progress.Destroy()
                                                except Exception:
                                                    pass
                                        except Exception:
                                            pass
                                        wx.MessageBox(f"Failed to install Argos package: {err}", "Install Error", wx.OK | wx.ICON_ERROR)
                                        try:
                                            if hasattr(self, 'translate_btn') and self.translate_btn:
                                                self.translate_btn.Enable()
                                        except Exception:
                                            pass
                                    wx.CallAfter(on_fail)
                            threading.Thread(target=install_worker, daemon=True).start()
                            return
                        else:
                            wx.MessageBox("Argos package not installed. Translation cancelled.", "Cancelled", wx.OK | wx.ICON_INFORMATION)
                            return
                    except Exception:
                        # Fall back to generic error handling below
                        pass
                # Generic error handling
                self.logger.error(f"Translation/tool error: {error}")
                wx.MessageBox(f"An error occurred: {error}", "Error", wx.OK | wx.ICON_ERROR)
                if source == 'tool':
                    try:
                        self.tool_button.Enable(True)
                        self.tool_results_list.Clear()
                        self.tool_results_list.Append(f"Error: {error}")
                    except Exception:
                        pass
                return

            if source == 'translation':
                self.logger.info("Processing translation completion event")

                # Extract data from the event immediately before it gets garbage collected
                result_data = getattr(event, 'result', None)
                usage_data = getattr(event, 'usage', {})

                self.logger.debug(f"Extracted result_data type: {type(result_data)}, entries count: {len(result_data) if result_data else 0}")
                self.logger.debug(f"Extracted usage_data: {usage_data}")

                if result_data is None:
                    self.logger.error("Translation result data is None!")
                    wx.MessageBox("Translation failed: No result data received", "Error", wx.OK | wx.ICON_ERROR)
                    return

                # Use CallAfter to safely handle UI updates after the modal dialog is closed
                self.logger.debug("Scheduling _on_translation_complete via CallAfter")
                wx.CallAfter(self._on_translation_complete, result_data, usage_data)
                self.logger.debug("CallAfter scheduled successfully")

            elif source == 'tool':
                self.logger.debug("Processing tool completion event")
                self.tool_results_list.Clear()
                if isinstance(event.result, list):
                    lines = [str(item) for item in event.result if str(item).strip()]
                else:
                    # One list item per line: a multi-line answer was a single
                    # unusable row before, so any advice had to be copy-pasted.
                    lines = [ln.strip() for ln in str(event.result).splitlines() if ln.strip()]
                if lines:
                    self.tool_results_list.Set(lines)
                    # Pre-select and focus so Enter replaces the translation
                    # straight away instead of doing nothing.
                    self.tool_results_list.SetSelection(0)
                    self.tool_results_list.SetFocus()
                self.tool_button.Enable(True)

        except Exception as e:
            self.logger.error(f"Exception in on_result: {e}", exc_info=True)
            wx.MessageBox(f"Critical error in result handling: {e}", "Error", wx.OK | wx.ICON_ERROR)

    def _on_translation_complete(self, result, usage):
        """Safely handles UI updates after translation is complete."""
        self.logger.info("_on_translation_complete called")

        try:
            self.logger.debug(f"Received result type: {type(result)}, entries: {len(result) if result else 0}")
            self.logger.debug(f"Received usage data: {usage}")

            # Validate result data
            if not result or not isinstance(result, list):
                self.logger.error(f"Invalid result data: {type(result)}")
                wx.MessageBox("Translation failed: Invalid result data", "Error", wx.OK | wx.ICON_ERROR)
                return

            self.translated_po_entries = result
            self.logger.debug(f"Set translated_po_entries, length: {len(self.translated_po_entries)}")

            # Calculate tokens safely
            prompt_tokens = usage.get('prompt_tokens', 0) if isinstance(usage, dict) else 0
            completion_tokens = usage.get('completion_tokens', 0) if isinstance(usage, dict) else 0
            total_tokens = prompt_tokens + completion_tokens

            self.logger.info(f"Translation completed - Entries: {len(self.translated_po_entries)}, Tokens: {total_tokens}")

            # Show completion message (distinct wording if the user cancelled,
            # since partial results are still kept and shown for review).
            was_cancelled = bool(usage.get('cancelled')) if isinstance(usage, dict) else False
            self.logger.debug("Showing completion message box")
            if was_cancelled:
                wx.MessageBox(
                    "Translation cancelled.\n\n"
                    "Entries already translated have been kept and are ready to "
                    f"review and save.\nTokens Used: {total_tokens:,}",
                    "Cancelled",
                    wx.OK | wx.ICON_INFORMATION
                )
            else:
                wx.MessageBox(
                    f"Translation complete!\nProcessed: {len(self.translated_po_entries)}\nTokens Used: {total_tokens:,}",
                    "Complete",
                    wx.OK | wx.ICON_INFORMATION
                )
            self.logger.debug("Completion message box shown successfully")

            # Check batch mode safely
            try:
                is_batch_mode = hasattr(self, 'batch_mode_checkbox') and self.batch_mode_checkbox.GetValue()
                self.logger.debug(f"Batch mode check: has_checkbox={hasattr(self, 'batch_mode_checkbox')}, value={is_batch_mode}")
            except Exception as e:
                self.logger.warning(f"Error checking batch mode, defaulting to False: {e}")
                is_batch_mode = False

            if is_batch_mode:
                self.logger.info("Batch mode enabled, auto-saving")
                self.on_save_changes(None, batch_mode=True)
            else:
                self.logger.info("Interactive mode, setting up review interface")
                self.current_entry_index = 0
                self.highest_reviewed_index = -1
                self.logger.debug("About to call show_review_interface")

                # Use CallLater to allow current event processing to complete first
                # This prevents crashes during UI finalization
                wx.CallLater(10, self._delayed_show_review_interface)
                self.logger.debug("Scheduled show_review_interface via CallLater")

        except Exception as e:
            self.logger.error(f"Critical exception in _on_translation_complete: {e}", exc_info=True)
            try:
                wx.MessageBox(f"Critical error during translation completion: {e}\n\nCheck mutt_debug.log for details",
                             "Critical Error", wx.OK | wx.ICON_ERROR)
            except Exception:
                self.logger.error("Could not even show error message box!")

    def _delayed_show_review_interface(self):
        """Delayed execution of show_review_interface to prevent UI finalization crashes."""
        self.logger.debug("_delayed_show_review_interface called")
        try:
            self.show_review_interface()
            self.logger.debug("show_review_interface completed successfully")
        except Exception as e:
            self.logger.error(f"Exception in _delayed_show_review_interface: {e}", exc_info=True)
            try:
                wx.MessageBox(f"Critical error creating review interface: {e}", "Error", wx.OK | wx.ICON_ERROR)
                self.show_main_app_content()
            except Exception:
                self.logger.error("Could not show error or fallback content")

    def show_translation_interface(self):
        self.logger.debug("show_translation_interface called.")
        create_translation_panel(self)
        self.logger.debug("show_translation_interface completed.")

    def on_src_lang_text_changed(self, event):
        self.source_language = self.src_lang_text.GetValue()

    def on_tgt_lang_text_changed(self, event):
        self.target_language = self.tgt_lang_text.GetValue()

    def _is_entry_untranslated(self, entry):
        return is_entry_untranslated(entry)

    def on_filter_entries(self, event=None):
        # All three filters (untranslated, file-ignore, sectional exclusion)
        # are evaluated against each entry's ORIGINAL index in
        # ``all_po_entries``. This is what makes exclusion rules behave
        # correctly in "Translate untranslated" mode: rule indices refer to
        # the full document, so they must never be applied to a pre-filtered
        # subset (which previously dropped unrelated strings instead).
        mode = self.translation_mode_radio.GetSelection()
        self.po_entries = select_entries_for_translation(
            self.all_po_entries,
            mode,
            self.file_ignore_rules,
            self.exclusion_manager,
        )

        self.entry_info_text.SetLabel(f"{len(self.po_entries)} of {len(self.all_po_entries)} entries selected.")
        self.translate_btn.Enable(bool(self.po_entries))
        self.panel.Layout()

    def show_review_interface(self):
        create_review_panel(self)
        # Fresh batch of entries becomes reviewable — snapshot the state now
        # so a crash before the user clicks anything still preserves the
        # machine-translated content.
        self.request_autosave()

    def on_chat_mode_change(self, event):
        """Safely handle chat mode changes with comprehensive error handling."""
        self.logger.debug("on_chat_mode_change called")

        try:
            if not hasattr(self, 'chat_mode_radio') or not self.chat_mode_radio:
                self.logger.error("chat_mode_radio not available - THIS IS THE CRASH POINT!")
                return

            self.logger.debug("Getting selected tool from chat_mode_radio")
            selected_tool = self.chat_mode_radio.GetStringSelection()
            self.logger.debug(f"Selected tool: {selected_tool}")

            # Check if this is a YAML-based mode
            yaml_mode_data = None
            yaml_modes_dir = Path("modes")
            if yaml_modes_dir.exists():
                for yaml_file in yaml_modes_dir.glob("*.mode.yaml"):
                    try:
                        with open(yaml_file, 'r', encoding='utf-8') as f:
                            mode_data = yaml.safe_load(f)
                            mode_name = mode_data.get("name", yaml_file.stem)
                            if mode_name == selected_tool:
                                yaml_mode_data = mode_data
                                break
                    except Exception:
                        pass
            
            # Check if this is a pre-coded Python mode
            python_mode_class = None
            if hasattr(self, 'python_modes'):
                python_mode_class = self.python_modes.get(selected_tool)
            
            is_variation = "Variations" in selected_tool
            is_chat = "Free Chat" in selected_tool
            is_yaml_mode = yaml_mode_data is not None
            is_python_mode = python_mode_class is not None
            self.logger.debug(f"Tool flags - variation: {is_variation}, chat: {is_chat}, yaml: {is_yaml_mode}, python: {is_python_mode}")

            # Hide all panels first
            if hasattr(self, 'variation_panel') and self.variation_panel:
                self.variation_panel.Show(False)
            
            if hasattr(self, 'generic_tool_panel') and self.generic_tool_panel:
                self.generic_tool_panel.Show(False)
            
            if hasattr(self, 'mode_specific_panel') and self.mode_specific_panel:
                self.mode_specific_panel.Show(False)
            
            # Remove any existing dynamic panel from the toolbox sizer
            if hasattr(self, 'dynamic_tool_panel') and self.dynamic_tool_panel:
                # Remove from parent sizer if it has been added
                if hasattr(self, 'toolbox_sizer'):
                    self.toolbox_sizer.Detach(self.dynamic_tool_panel)
                self.dynamic_tool_panel.Destroy()
                delattr(self, 'dynamic_tool_panel')
            
            if hasattr(self, 'dynamic_tool_data_store'):
                delattr(self, 'dynamic_tool_data_store')
            
            # Clear mode-specific panel
            if hasattr(self, 'mode_specific_sizer'):
                self.mode_specific_sizer.Clear(True)
            
            # Show appropriate panel
            if is_variation and hasattr(self, 'variation_panel'):
                self.logger.debug("Showing variation panel")
                self.variation_panel.Show(True)
            
            elif is_chat and hasattr(self, 'generic_tool_panel'):
                self.logger.debug("Showing generic tool panel")
                self.generic_tool_panel.Show(True)
            
            elif is_yaml_mode:
                self.logger.debug("Creating dynamic panel for YAML mode")
                # Create dynamic panel for YAML mode
                self.dynamic_tool_data_store = {}
                ui_config = yaml_mode_data.get("ui", [])
                if ui_config:
                    self.dynamic_tool_panel = create_dynamic_panel(self.panel, ui_config, self.dynamic_tool_data_store)
                    # Add to toolbox sizer if it exists
                    if hasattr(self, 'toolbox_sizer'):
                        # Insert the dynamic panel before the tool button (which is at position -3 from the end)
                        # We need to be careful about the position
                        self.toolbox_sizer.Insert(len(self.toolbox_sizer.GetChildren()) - 3, self.dynamic_tool_panel, 0, wx.EXPAND | wx.ALL, 5)
                    self.dynamic_tool_panel.Show(True)
            elif is_python_mode and hasattr(self, 'mode_specific_panel') and hasattr(self, 'mode_specific_sizer'):
                self.logger.debug(f"Creating mode-specific panel for {selected_tool}")
                # Instantiate the Python mode
                from ai_translator import AITranslator
                active_provider = self.config.get("last_provider")
                settings = self.config.get("providers", {}).get(active_provider, {})
                translator = AITranslator(active_provider, settings.get("api_key"), settings.get("api_model"), temperature=self.config.get("temperature", 0.7), max_tokens=self.config.get("max_tokens", 4000), extra_settings=settings)
                
                mode_instance = instantiate_mode(python_mode_class, self, translator)
                
                # Store reference to mode instance for later use
                if not hasattr(self, 'instantiated_modes'):
                    self.instantiated_modes = {}
                self.instantiated_modes[selected_tool] = mode_instance
                
                # Get the UI layout from the mode
                try:
                    ui_layout = mode_instance.get_ui_layout(self.mode_specific_panel)
                    if ui_layout:
                        self.mode_specific_sizer.Add(ui_layout, 1, wx.EXPAND)
                except Exception as e:
                    self.logger.error(f"Error getting UI layout for mode {selected_tool}: {e}")
                
                self.mode_specific_panel.Show(True)
            else:
                # For other pre-coded Python modes without specific UI, hide all special panels
                self.logger.debug("Hiding all special panels for pre-coded mode")
            
            self.logger.debug("Calling panel.Layout()")
            if hasattr(self, 'panel') and self.panel:
                self.panel.Layout()
            self.logger.debug("Panel layout completed successfully")

        except Exception as e:
            self.logger.error(f"CRITICAL EXCEPTION in on_chat_mode_change: {e}", exc_info=True)
    def on_results_key_down(self, event):
        if event.GetKeyCode() in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]: self.on_variation_select(event)
        else: event.Skip()
    def on_variation_select(self, event):
        selected_text = self.tool_results_list.GetStringSelection()
        if selected_text: self.tgt_text_ctrl.SetValue(re.sub(r"^\d+\.\s*", "", selected_text))

    def on_tool_execute(self, event):
        self.tool_button.Disable(); self.tool_results_list.Clear(); self.tool_results_list.Append("Processing...")
        threading.Thread(target=run_tool_thread, args=(self,), daemon=True).start()
    def on_prev_entry(self, event):
        self.logger.debug("on_prev_entry called")
        try:
            if self.current_entry_index > 0:
                self.save_current_entry_changes()
                self.current_entry_index -= 1
                self.display_current_entry()
        except Exception as e:
            self.logger.error(f"Exception in on_prev_entry: {e}", exc_info=True)

    def on_next_entry(self, event):
        self.logger.debug("on_next_entry called")
        try:
            if self.current_entry_index < len(self.translated_po_entries) - 1:
                self.save_current_entry_changes()
                self.current_entry_index += 1
                self.display_current_entry()
        except Exception as e:
            self.logger.error(f"Exception in on_next_entry: {e}", exc_info=True)

    def save_current_entry_changes(self):
        self.logger.debug("save_current_entry_changes called")
        try:
            if 0 <= self.current_entry_index < len(self.translated_po_entries):
                if hasattr(self, 'tgt_text_ctrl') and self.tgt_text_ctrl:
                    entry = self.translated_po_entries[self.current_entry_index]
                    # For a plural entry this writes msgstr[n]; msgstr itself is
                    # ignored by gettext once msgid_plural is present.
                    set_target_for_form(entry, self.current_plural_form, self.tgt_text_ctrl.GetValue())
                    self.request_autosave()
                else:
                    self.logger.warning("tgt_text_ctrl not available in save_current_entry_changes")
        except Exception as e:
            self.logger.error(f"Exception in save_current_entry_changes: {e}", exc_info=True)

    def _update_plural_selector(self, entry):
        """Show the plural-form picker for entries that have a msgid_plural,
        hide it for ordinary ones, and keep ``current_plural_form`` valid."""
        choice = getattr(self, 'plural_choice', None)
        label = getattr(self, 'plural_label', None)
        forms = plural_forms(entry)
        # Moving to a different entry always lands on the singular form.
        if getattr(self, '_plural_anchor_index', None) != self.current_entry_index:
            self._plural_anchor_index = self.current_entry_index
            self.current_plural_form = forms[0] if forms else None
        if not forms:
            self.current_plural_form = None
        elif self.current_plural_form not in forms:
            self.current_plural_form = forms[0]
        if not choice or not label:
            return
        try:
            if forms:
                labels = [form_label(f) for f in forms]
                if choice.GetStrings() != labels:
                    choice.SetItems(labels)
                choice.SetSelection(forms.index(self.current_plural_form))
                label.Show()
                choice.Show()
            else:
                label.Hide()
                choice.Hide()
            self.panel.Layout()
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Plural selector update failed: {e}", exc_info=True)

    def _update_notes(self, entry):
        """Render the PO comments for this entry into the read-only notes box."""
        ctrl = getattr(self, 'notes_text_ctrl', None)
        if not ctrl:
            return
        ctrl.SetValue(format_entry_notes(entry))

    def display_current_entry(self):
        """Safely display current entry with comprehensive error handling."""
        self.logger.debug(f"display_current_entry called, index: {self.current_entry_index}")

        try:
            if not (0 <= self.current_entry_index < len(self.translated_po_entries)):
                self.logger.warning(f"Invalid entry index: {self.current_entry_index}, total entries: {len(self.translated_po_entries)}")
                return

            self.highest_reviewed_index = max(self.highest_reviewed_index, self.current_entry_index)
            entry = self.translated_po_entries[self.current_entry_index]
            self.logger.debug(f"Processing entry: {entry.get('msgid', '')[:50]}...")

            self._update_plural_selector(entry)
            self._update_notes(entry)

            # Safely access UI controls with existence checks
            if hasattr(self, 'src_text_ctrl') and self.src_text_ctrl:
                self.logger.debug("Setting source text control value")
                self.src_text_ctrl.SetValue(source_for_form(entry, self.current_plural_form))
                self.logger.debug("Source text control updated successfully")
            else:
                self.logger.error("src_text_ctrl not available - THIS IS THE CRASH POINT!")
                return

            if hasattr(self, 'tgt_text_ctrl') and self.tgt_text_ctrl:
                self.logger.debug("Setting target text control value")
                self.tgt_text_ctrl.SetValue(target_for_form(entry, self.current_plural_form))
                self.logger.debug("Target text control updated successfully")
            else:
                self.logger.error("tgt_text_ctrl not available - THIS IS THE CRASH POINT!")
                return

            if hasattr(self, 'entry_counter_text') and self.entry_counter_text:
                self.logger.debug("Setting entry counter text")
                self.entry_counter_text.SetLabel(f"Entry {self.current_entry_index + 1} of {len(self.translated_po_entries)}")
                self.logger.debug("Entry counter updated successfully")
            else:
                self.logger.error("entry_counter_text not available - THIS IS THE CRASH POINT!")
                return

            if hasattr(self, 'prev_btn') and self.prev_btn:
                self.prev_btn.Enable(self.current_entry_index > 0)
                self.logger.debug("Previous button state updated")
            else:
                self.logger.warning("prev_btn not available")

            if hasattr(self, 'next_btn') and self.next_btn:
                self.next_btn.Enable(self.current_entry_index < len(self.translated_po_entries) - 1)
                self.logger.debug("Next button state updated")
            else:
                self.logger.warning("next_btn not available")

            self.logger.debug("display_current_entry completed successfully")

        except Exception as e:
            self.logger.error(f"CRITICAL EXCEPTION in display_current_entry: {e}", exc_info=True)

    def on_load_ignore_list(self, event):
        on_load_ignore_list(self, event)

    def on_select_termbase(self, event):
        on_select_termbase(self, event)

    def on_save_changes(self, event, batch_mode=False):
        on_save_changes(self, event, batch_mode)

    def on_save_as(self, event):
        on_save_changes(self, event, batch_mode=False, save_as=True)

    def on_save_project(self, event):
        on_save_project(self, event)

    def on_show_statistics(self, event):
        if not self.all_po_entries:
            wx.MessageBox("Open a file first to see translation statistics.", "Info", wx.OK | wx.ICON_INFORMATION)
            return
        from mutt.ui.dialogs.stats import TranslationStatsDialog
        with TranslationStatsDialog(
            self, self.all_po_entries, self.exclusion_manager, self.file_ignore_rules
        ) as dlg:
            dlg.ShowModal()

    def on_export_exclusion_rules(self, event):
        if not self.exclusion_manager.get_rules():
            wx.MessageBox("No exclusion rules to export.", "Info", wx.OK | wx.ICON_INFORMATION)
            return

        with wx.FileDialog(self, "Export Exclusion Rules",
                           wildcard="JSON files (*.json)|*.json",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return

            pathname = fileDialog.GetPath()
            success, message = self.exclusion_manager.export_rules_to_file(pathname)
            if success:
                wx.MessageBox(message, "Export Successful", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox(message, "Export Failed", wx.OK | wx.ICON_ERROR)

    def _save_project_file(self, path):
        _save_project_file(self, path)

    def _load_project_file(self, path):
        _load_project_file(self, path)
        if hasattr(self, 'src_lang_text'):
            self.src_lang_text.SetValue(self.source_language)
        if hasattr(self, 'tgt_lang_text'):
            self.tgt_lang_text.SetValue(self.target_language)
        # Capture the loaded project into autosave so a crash right after
        # opening a project still preserves the user's work.
        self.request_autosave()

    def _update_translation_memory(self, saved_entries):
        _update_translation_memory(self, saved_entries)

    # ------------------------------------------------------------ autosave
    def _autosave_snapshot(self):
        """Build a JSON-serialisable snapshot from UI-thread state.

        Must only be called from the wx UI thread so mutable collections
        (``translated_po_entries``, exclusion rules) can be copied without
        risk of a concurrent mutation tearing the snapshot.
        """
        try:
            if not self.translated_po_entries and not self.po_file_path:
                return None
            exclusion_rules = []
            try:
                exclusion_rules = self.exclusion_manager.to_json()
            except Exception:  # noqa: BLE001
                pass
            # Copy entries into new dicts so the worker thread can read them
            # without ever touching wx-owned objects.
            review_entries = [
                dict(entry) if isinstance(entry, dict) else entry
                for entry in self.translated_po_entries
            ]
            # The full document travels with the snapshot: without it a
            # recovered session can no longer merge the reviewed subset back
            # on save, and every filtered-out string would be lost again.
            all_entries = [
                dict(entry) if isinstance(entry, dict) else entry
                for entry in self.all_po_entries
            ]
            return {
                "original_file": self.po_file_path,
                "file_type": self.file_type,
                "review_entries": review_entries,
                "all_entries": all_entries,
                "current_index": self.current_entry_index,
                "highest_reviewed_index": self.highest_reviewed_index,
                "source_language": self.source_language,
                "target_language": self.target_language,
                "exclusion_rules": exclusion_rules,
            }
        except Exception:  # noqa: BLE001
            self.logger.warning("Autosave snapshot failed", exc_info=True)
            return None

    def request_autosave(self):
        """Safe, debounced trigger — call on any state-changing edit.

        Builds the snapshot synchronously on the wx UI thread before handing
        it to the background writer, avoiding any cross-thread reads of
        wx-owned state.
        """
        mgr = getattr(self, "autosave_manager", None)
        if mgr is None:
            return
        snapshot = self._autosave_snapshot()
        if snapshot is None:
            return
        mgr.request_save(snapshot=snapshot)

    def _offer_autosave_recovery(self):
        """On startup, scan for autosaves from crashed sessions."""
        mgr = getattr(self, "autosave_manager", None)
        if mgr is None:
            return
        try:
            sessions = mgr.find_recoverable_sessions()
        except Exception:  # noqa: BLE001
            self.logger.warning("Recovery scan failed", exc_info=True)
            return
        for session in sessions:
            self._prompt_recovery(session)

    def _prompt_recovery(self, session: "RecoverableSession"):
        original = session.original_file or "(unknown file)"
        ts = session.timestamp.isoformat() if session.timestamp else "(unknown time)"
        msg = (
            f"A previous MUTT session appears to have ended unexpectedly.\n\n"
            f"File: {original}\n"
            f"Last autosave: {ts}\n\n"
            f"Recover this work?"
        )
        try:
            choice = wx.MessageBox(
                msg, "Recover Unsaved Work",
                wx.YES_NO | wx.ICON_QUESTION,
            )
        except Exception:  # noqa: BLE001
            return
        if choice == wx.YES:
            try:
                self._apply_recovered_session(session.data)
                wx.MessageBox(
                    "Session recovered. Review and save to a new file.",
                    "Recovery Complete", wx.OK | wx.ICON_INFORMATION,
                )
            except Exception as exc:  # noqa: BLE001
                self.logger.error("Recovery failed", exc_info=True)
                wx.MessageBox(
                    f"Recovery failed: {exc}", "Error", wx.OK | wx.ICON_ERROR,
                )
                return
        # Either recovered or declined — clean up the file either way.
        self.autosave_manager.discard_session_file(session)

    @staticmethod
    def _safe_recovered_path(raw):
        """Only trust recovered file paths that are sane local absolute paths.

        Rejects UNC paths (``\\\\host\\share\\...``) and any non-absolute or
        non-string value. This prevents a crafted autosave file from
        coercing MUTT into opening an arbitrary or network path on recovery.
        """
        if not isinstance(raw, str) or not raw:
            return None
        if raw.startswith("\\\\") or raw.startswith("//"):
            return None
        try:
            from pathlib import Path as _Path
            candidate = _Path(raw)
        except Exception:  # noqa: BLE001
            return None
        if not candidate.is_absolute():
            return None
        return str(candidate)

    def _apply_recovered_session(self, data):
        """Restore in-memory state from a recovered autosave payload."""
        self.po_file_path = self._safe_recovered_path(data.get("original_file"))
        file_type = data.get("file_type")
        self.file_type = file_type if isinstance(file_type, str) else None
        entries = data.get("review_entries", [])
        if not isinstance(entries, list):
            entries = []
        self.translated_po_entries = list(entries)
        all_entries = data.get("all_entries")
        # Snapshots written before "all_entries" existed only hold the
        # reviewed subset; that is then all the document we have.
        self.all_po_entries = (
            list(all_entries) if isinstance(all_entries, list) and all_entries
            else list(self.translated_po_entries)
        )
        try:
            self.current_entry_index = int(data.get("current_index", 0) or 0)
        except (TypeError, ValueError):
            self.current_entry_index = 0
        try:
            self.highest_reviewed_index = int(
                data.get("highest_reviewed_index", self.current_entry_index) or 0
            )
        except (TypeError, ValueError):
            self.highest_reviewed_index = self.current_entry_index
        src_lang = data.get("source_language")
        if isinstance(src_lang, str):
            self.source_language = src_lang
        tgt_lang = data.get("target_language")
        if isinstance(tgt_lang, str):
            self.target_language = tgt_lang
        try:
            from exprules import ExclusionManager
            rules = data.get("exclusion_rules", [])
            if isinstance(rules, list):
                self.exclusion_manager = ExclusionManager.from_json(rules)
        except Exception:  # noqa: BLE001
            pass
        if self.translated_po_entries:
            self.show_review_interface()

    def on_close_frame(self, event):
        """Clean shutdown: flush autosave and remove the session file."""
        try:
            mgr = getattr(self, "autosave_manager", None)
            if mgr is not None:
                mgr.stop(flush=True, delete=True)
        except Exception:  # noqa: BLE001
            self.logger.warning("Autosave shutdown failed", exc_info=True)
        event.Skip()


class MuttApp(wx.App):
    def OnInit(self):
        MainFrame(None, "MUTT")
        return True

if __name__ == "__main__":
    app = MuttApp()
    app.MainLoop()