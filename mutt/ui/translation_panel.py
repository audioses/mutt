import wx
from .language_panel import create_language_panel

def create_translation_panel(frame):
    frame.logger.debug("create_translation_panel called.")
    frame.panel.DestroyChildren()
    main_sizer = wx.BoxSizer(wx.VERTICAL)
    frame.entry_info_text = wx.StaticText(frame.panel, label=f"Loaded {len(frame.all_po_entries)} entries")
    main_sizer.Add(frame.entry_info_text, 0, wx.ALL|wx.EXPAND, 10)
    frame.translation_mode_radio = wx.RadioBox(frame.panel, label="Mode", choices=["Translate untranslated", "Translate all", "Update fuzzy (outdated)"], style=wx.RA_SPECIFY_ROWS)
    main_sizer.Add(frame.translation_mode_radio, 0, wx.ALL|wx.EXPAND, 10)

    # Translation method selection
    method_choices = ["LLM Translation", "Human Translation", "Argos Translate", "HuggingFace Neural Translation (Placeholder)"]
    frame.translation_method_radio = wx.RadioBox(frame.panel, label="Translation Method",
                                                 choices=method_choices,
                                                 style=wx.RA_SPECIFY_ROWS)
    
    # Set the selection based on the last saved choice
    last_method = frame.config.get('last_translation_method', 'LLM Translation')
    if last_method in method_choices:
        frame.translation_method_radio.SetStringSelection(last_method)
    else:
        frame.translation_method_radio.SetSelection(0) # Default to LLM

    main_sizer.Add(frame.translation_method_radio, 0, wx.ALL|wx.EXPAND, 10)

    # Create and add the language panel
    lang_sizer = create_language_panel(frame, frame.panel)
    main_sizer.Add(lang_sizer, 0, wx.EXPAND | wx.ALL, 10)
    
    main_sizer.Add(wx.StaticText(frame.panel, label="Context Prompt (type to add new):"), 0, wx.LEFT|wx.TOP, 10)
    prompt_names = [p["name"] for p in frame.config.get("prompts", []) if not p.get("system")]
    frame.prompt_combo = wx.ComboBox(frame.panel, value="", choices=prompt_names)
    main_sizer.Add(frame.prompt_combo, 0, wx.ALL|wx.EXPAND, 10)
    frame.batch_mode_checkbox = wx.CheckBox(frame.panel, label="Batch Mode (Auto-save)")
    main_sizer.Add(frame.batch_mode_checkbox, 0, wx.ALL, 10)
    frame.translate_btn = wx.Button(frame.panel, label="Translate")
    main_sizer.Add(frame.translate_btn, 0, wx.ALL|wx.CENTER, 10)
    frame.panel.SetSizerAndFit(main_sizer)
    frame.logger.debug("Calling panel.Layout() in create_translation_panel.")
    frame.panel.Layout()
    frame.translation_mode_radio.Bind(wx.EVT_RADIOBOX, frame.on_filter_entries)
    frame.translate_btn.Bind(wx.EVT_BUTTON, frame.on_translate)
    frame.on_filter_entries(None)
    frame.logger.debug("create_translation_panel completed.")
