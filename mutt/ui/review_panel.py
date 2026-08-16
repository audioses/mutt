import wx
from .language_panel import create_language_panel
import yaml
from pathlib import Path
from mutt.logic.mode_loader import discover_python_modes

def create_review_panel(frame):
    frame.logger.debug("create_review_panel called.")
    frame.logger.info("show_review_interface called")

    try:
        frame.logger.debug("Destroying panel children")
        frame.panel.DestroyChildren()
        frame.logger.debug("Panel children destroyed successfully")

        if not frame.translated_po_entries:
            frame.logger.warning("No translated entries to review")
            wx.MessageBox("No entries to review.", "Info")
            frame.show_main_app_content()
            return

        frame.logger.debug(f"Creating review interface for {len(frame.translated_po_entries)} entries")

        # Create main sizer
        frame.logger.debug("Creating main sizer")
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Language panel
        lang_sizer = create_language_panel(frame, frame.panel)
        main_sizer.Add(lang_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # Navigation section
        frame.logger.debug("Creating navigation controls")
        nav_sizer = wx.BoxSizer(wx.HORIZONTAL)
        frame.prev_btn = wx.Button(frame.panel, label="< Previous (Alt+P/Up)")
        frame.next_btn = wx.Button(frame.panel, label="Next (Alt+N/Down) >")
        frame.entry_counter_text = wx.StaticText(frame.panel)

        nav_sizer.Add(frame.prev_btn, 0, wx.ALL, 5)
        nav_sizer.Add(frame.entry_counter_text, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5)
        nav_sizer.Add(frame.next_btn, 0, wx.ALL, 5)
        main_sizer.Add(nav_sizer, 0, wx.EXPAND|wx.ALL, 10)
        frame.logger.debug("Navigation controls created successfully")

        # Plural form selector — only shown for entries that have a
        # msgid_plural. The label must precede the control so screen readers
        # announce it.
        frame.plural_label = wx.StaticText(frame.panel, label="Plural form (Alt+U):")
        frame.plural_choice = wx.Choice(frame.panel, choices=[])
        main_sizer.Add(frame.plural_label, 0, wx.ALL, 5)
        main_sizer.Add(frame.plural_choice, 0, wx.EXPAND|wx.ALL, 5)
        frame.plural_label.Hide()
        frame.plural_choice.Hide()

        # Source and target text sections
        frame.logger.debug("Creating text controls")
        main_sizer.Add(wx.StaticText(frame.panel, label="Source Text (Alt+Left):"), 0, wx.ALL, 5)
        frame.src_text_ctrl = wx.TextCtrl(frame.panel, style=wx.TE_MULTILINE|wx.TE_READONLY)
        main_sizer.Add(frame.src_text_ctrl, 1, wx.EXPAND|wx.ALL, 5)
        main_sizer.Add(wx.StaticText(frame.panel, label="Translated Text (Alt+Right):"), 0, wx.ALL, 5)
        frame.tgt_text_ctrl = wx.TextCtrl(frame.panel, style=wx.TE_MULTILINE)
        main_sizer.Add(frame.tgt_text_ctrl, 1, wx.EXPAND|wx.ALL, 5)
        frame.logger.debug("Text controls created successfully")

        # Comments from the PO file (translator notes, extracted comments,
        # source references). Read-only but focusable so it can be read.
        main_sizer.Add(wx.StaticText(frame.panel, label="Comments && Notes (Alt+C):"), 0, wx.ALL, 5)
        frame.notes_text_ctrl = wx.TextCtrl(frame.panel, style=wx.TE_MULTILINE|wx.TE_READONLY)
        main_sizer.Add(frame.notes_text_ctrl, 1, wx.EXPAND|wx.ALL, 5)

        # Toolbox section
        frame.logger.debug("Creating toolbox section")
        toolbox_box = wx.StaticBox(frame.panel, label="Translator's Toolbox")
        frame.toolbox_sizer = wx.StaticBoxSizer(toolbox_box, wx.VERTICAL)
        toolbox_sizer = frame.toolbox_sizer

        # Load both pre-coded Python modes and YAML mode files
        frame.tool_choices = []
        frame.python_modes = {}  # Store references to python mode instances
        
        # Load pre-coded Python modes
        python_modes = discover_python_modes()
        python_tool_choices = list(python_modes.keys())
        frame.tool_choices.extend(python_tool_choices)
        frame.python_modes.update(python_modes)
        
        # Load YAML mode files
        yaml_modes_dir = Path("modes")
        if yaml_modes_dir.exists():
            for yaml_file in yaml_modes_dir.glob("*.mode.yaml"):
                try:
                    with open(yaml_file, 'r', encoding='utf-8') as f:
                        mode_data = yaml.safe_load(f)
                        mode_name = mode_data.get("name", yaml_file.stem)
                        if mode_name not in frame.tool_choices:
                            frame.tool_choices.append(mode_name)
                except Exception as e:
                    frame.logger.error(f"Error loading YAML mode {yaml_file}: {e}")
        
        frame.logger.debug(f"Found {len(frame.tool_choices)} tool choices: {frame.tool_choices}")

        # A dropdown rather than a RadioBox: the 3-column RadioBox this
        # replaced could only be arrowed within one column, leaving most tools
        # unreachable from the keyboard. A single-column RadioBox would fix
        # that but adds a row per tool to an already tall panel; a Choice is
        # one row and Up/Down walks every entry. (Attribute name kept — the
        # tool handlers read chat_mode_radio.GetStringSelection().)
        if not frame.tool_choices:
            frame.logger.warning("No tool choices available")
        toolbox_sizer.Add(wx.StaticText(frame.panel, label="Tool Mode:"), 0, wx.ALL, 5)
        frame.chat_mode_radio = wx.Choice(frame.panel, choices=frame.tool_choices or ["No tools available"])
        frame.chat_mode_radio.SetSelection(0)  # a Choice starts unselected
        toolbox_sizer.Add(frame.chat_mode_radio, 0, wx.ALL | wx.EXPAND, 5)

        # Variation panel
        frame.logger.debug("Creating variation panel")
        frame.variation_panel = wx.Panel(frame.panel)
        variation_sizer = wx.BoxSizer(wx.VERTICAL)
        var_row1 = wx.BoxSizer(wx.HORIZONTAL)

        var_row1.Add(wx.StaticText(frame.variation_panel, label="Count:"), 0, wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, 5)
        frame.variation_count = wx.SpinCtrl(frame.variation_panel, value="3", min=1, max=10)
        var_row1.Add(frame.variation_count, 0, wx.RIGHT, 10)
        var_row1.Add(wx.StaticText(frame.variation_panel, label="Style:"), 0, wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, 5)
        frame.variation_style = wx.ComboBox(frame.variation_panel, choices=["Default", "Formal", "Informal", "Concise"])
        frame.variation_style.SetSelection(0)
        var_row1.Add(frame.variation_style, 1, wx.EXPAND)
        variation_sizer.Add(var_row1, 0, wx.EXPAND | wx.BOTTOM, 5)
        variation_sizer.Add(wx.StaticText(frame.variation_panel, label="Custom Instruction (optional):"), 0, wx.TOP, 5)
        frame.variation_custom_prompt = wx.TextCtrl(frame.variation_panel, style=wx.TE_PROCESS_ENTER)
        variation_sizer.Add(frame.variation_custom_prompt, 0, wx.EXPAND)
        frame.variation_panel.SetSizer(variation_sizer)
        toolbox_sizer.Add(frame.variation_panel, 0, wx.EXPAND|wx.ALL, 5)
        frame.logger.debug("Variation panel created successfully")

        # Generic tool panel
        frame.logger.debug("Creating generic tool panel")
        frame.generic_tool_panel = wx.Panel(frame.panel)
        generic_sizer = wx.BoxSizer(wx.HORIZONTAL)
        generic_sizer.Add(wx.StaticText(frame.generic_tool_panel, label="Input:"), 0, wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, 5)
        frame.tool_input = wx.TextCtrl(frame.generic_tool_panel, style=wx.TE_PROCESS_ENTER)
        generic_sizer.Add(frame.tool_input, 1, wx.EXPAND)
        frame.generic_tool_panel.SetSizer(generic_sizer)
        toolbox_sizer.Add(frame.generic_tool_panel, 0, wx.EXPAND|wx.ALL, 5)

        # Mode-specific tool panel
        frame.logger.debug("Creating mode-specific tool panel")
        frame.mode_specific_panel = wx.Panel(frame.panel)
        frame.mode_specific_sizer = wx.BoxSizer(wx.VERTICAL)
        frame.mode_specific_panel.SetSizer(frame.mode_specific_sizer)
        toolbox_sizer.Add(frame.mode_specific_panel, 0, wx.EXPAND|wx.ALL, 5)

        # Tool button and results
        frame.logger.debug("Creating tool button and results list")
        frame.tool_button = wx.Button(frame.panel, label="Execute Tool")
        toolbox_sizer.Add(frame.tool_button, 0, wx.ALL|wx.ALIGN_RIGHT, 5)
        toolbox_sizer.Add(wx.StaticText(frame.panel, label="Results (Double-click or Enter to use):"), 0, wx.ALL, 5)
        frame.tool_results_list = wx.ListBox(frame.panel, style=wx.LB_SINGLE, size=(-1, 100))
        toolbox_sizer.Add(frame.tool_results_list, 1, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(toolbox_sizer, 0, wx.ALL | wx.EXPAND, 10)
        frame.logger.debug("Toolbox section completed successfully")

        # Save buttons
        frame.logger.debug("Creating save buttons")
        save_sizer = wx.BoxSizer(wx.HORIZONTAL)
        save_btn = wx.Button(frame.panel, label="Save (Ctrl+S)")
        save_as_btn = wx.Button(frame.panel, label="Save As...")
        save_project_btn = wx.Button(frame.panel, label="Save Project")
        save_sizer.Add(save_project_btn, 0, wx.ALL, 5)
        save_sizer.Add(save_as_btn, 0, wx.ALL, 5)
        save_sizer.Add(save_btn, 0, wx.ALL, 5)
        main_sizer.Add(save_sizer, 0, wx.CENTER|wx.ALL, 10)

        # Set sizer and layout
        frame.logger.debug("Setting panel sizer and layout")
        frame.panel.SetSizerAndFit(main_sizer)

        # Bind events
        frame.logger.debug("Binding events")
        frame.prev_btn.Bind(wx.EVT_BUTTON, frame.on_prev_entry)
        frame.next_btn.Bind(wx.EVT_BUTTON, frame.on_next_entry)
        frame.plural_choice.Bind(wx.EVT_CHOICE, frame.on_plural_form_change)
        save_btn.Bind(wx.EVT_BUTTON, frame.on_save_changes)
        save_as_btn.Bind(wx.EVT_BUTTON, frame.on_save_as)
        save_project_btn.Bind(wx.EVT_BUTTON, frame.on_save_project)
        frame.tool_button.Bind(wx.EVT_BUTTON, frame.on_tool_execute)
        frame.tool_input.Bind(wx.EVT_TEXT_ENTER, frame.on_tool_execute)
        frame.variation_custom_prompt.Bind(wx.EVT_TEXT_ENTER, frame.on_tool_execute)
        frame.chat_mode_radio.Bind(wx.EVT_CHOICE, frame.on_chat_mode_change)
        frame.tool_results_list.Bind(wx.EVT_LISTBOX_DCLICK, frame.on_variation_select)
        frame.tool_results_list.Bind(wx.EVT_KEY_DOWN, frame.on_results_key_down)
        frame.logger.debug("All events bound successfully")

        # Final setup
        frame.logger.debug("Calling display_current_entry")
        frame.display_current_entry()
        frame.logger.debug("display_current_entry completed")

        frame.logger.debug("Calling on_chat_mode_change")
        frame.on_chat_mode_change(None)
        frame.logger.debug("on_chat_mode_change completed")

        frame.logger.debug("Calling panel.Layout() in create_review_panel.")
        frame.panel.Layout()
        frame.logger.info("show_review_interface completed successfully")
        frame.logger.debug("create_review_panel completed.")

    except Exception as e:
        frame.logger.error(f"CRITICAL: Exception in create_review_panel: {e}", exc_info=True)
        try:
            wx.MessageBox(f"Failed to create review interface: {e}\n\nCheck mutt_debug.log for details",
                         "Interface Error", wx.OK | wx.ICON_ERROR)
        except Exception:
            frame.logger.error("Could not show interface error dialog")
        # Try to show main app content as fallback
        try:
            frame.logger.debug("Attempting fallback to main app content")
            frame.show_main_app_content()
        except Exception as fallback_error:
            frame.logger.error(f"Could not show fallback content: {fallback_error}")
