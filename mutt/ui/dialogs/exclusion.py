import wx

class AddExclusionRuleDialog(wx.Dialog):
    def __init__(self, parent, all_entries, exclusion_manager):
        super(AddExclusionRuleDialog, self).__init__(parent, title="Add Exclusion Rule", size=(600, 500))
        self.all_entries = all_entries # Keep reference to full entries for original indices
        self.all_entries_msgids_full = [entry['msgid'] for entry in all_entries]
        self.exclusion_manager = exclusion_manager
        
        self.original_entries_map = {} # Maps listbox display index to original all_entries index
        self.start_original_idx = -1
        self.end_original_idx = -1
        self.start_marker_display = "" # For UI display only
        self.end_marker_display = ""   # For UI display only

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        vbox.Add(wx.StaticText(panel, label="Select the start and (optional) end entries for the section to exclude."), 0, wx.ALL, 10)

        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_sizer.Add(wx.StaticText(panel, label="Search:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.search_ctrl = wx.SearchCtrl(panel)
        search_sizer.Add(self.search_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        vbox.Add(search_sizer, 0, wx.EXPAND | wx.ALL, 5)

        self.entry_listbox = wx.ListBox(panel, style=wx.LB_SINGLE)
        vbox.Add(self.entry_listbox, 1, wx.EXPAND | wx.ALL, 5)
        
        self.populate_entry_listbox() # Initial population

        marker_box = wx.StaticBox(panel, label="Selected Markers")
        marker_sizer = wx.StaticBoxSizer(marker_box, wx.VERTICAL)
        
        start_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.set_start_btn = wx.Button(panel, label="Set as Start Marker")
        start_sizer.Add(self.set_start_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.start_marker_text = wx.TextCtrl(panel, style=wx.TE_READONLY | wx.TE_LEFT)
        start_sizer.Add(self.start_marker_text, 1, wx.EXPAND)
        marker_sizer.Add(start_sizer, 0, wx.EXPAND | wx.ALL, 5)

        end_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.set_end_btn = wx.Button(panel, label="Set as End Marker")
        end_sizer.Add(self.set_end_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.end_marker_text = wx.TextCtrl(panel, style=wx.TE_READONLY | wx.TE_LEFT)
        end_sizer.Add(self.end_marker_text, 1, wx.EXPAND)
        marker_sizer.Add(end_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        vbox.Add(marker_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK)
        cancel_btn = wx.Button(panel, wx.ID_CANCEL)
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()
        vbox.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        panel.SetSizer(vbox)

        self.search_ctrl.Bind(wx.EVT_TEXT, self.on_search)
        self.set_start_btn.Bind(wx.EVT_BUTTON, self.on_set_start)
        self.set_end_btn.Bind(wx.EVT_BUTTON, self.on_set_end)
        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK) # Bind OK button to on_ok method

    def populate_entry_listbox(self):
        self.entry_listbox.Clear()
        self.original_entries_map = {}
        display_idx = 0
        search_term = self.search_ctrl.GetValue().lower()

        for original_idx, msgid in enumerate(self.all_entries_msgids_full):
            # Check if this entry is already excluded by an existing rule
            if not self.exclusion_manager.is_excluded_by_index(original_idx, self.all_entries_msgids_full):
                if not search_term or search_term in msgid.lower():
                    self.entry_listbox.Append(msgid)
                    self.original_entries_map[display_idx] = original_idx
                    display_idx += 1

    def on_search(self, event):
        self.populate_entry_listbox()

    def on_set_start(self, event):
        selected_display_idx = self.entry_listbox.GetSelection()
        if selected_display_idx != wx.NOT_FOUND:
            self.start_original_idx = self.original_entries_map[selected_display_idx]
            self.start_marker_display = self.all_entries_msgids_full[self.start_original_idx]
            self.set_start_btn.SetLabel(f"Start: {self.start_marker_display[:20]}...")  # Truncate for button label
            self.start_marker_text.SetValue(self.start_marker_display)

    def on_set_end(self, event):
        selected_display_idx = self.entry_listbox.GetSelection()
        if selected_display_idx != wx.NOT_FOUND:
            self.end_original_idx = self.original_entries_map[selected_display_idx]
            self.end_marker_display = self.all_entries_msgids_full[self.end_original_idx]
            self.set_end_btn.SetLabel(f"End: {self.end_marker_display[:20]}...")  # Truncate for button label
            self.end_marker_text.SetValue(self.end_marker_display)
    
    def on_ok(self, event):
        # Validation logic using original indices
        if self.start_original_idx == -1 and self.end_original_idx != -1:
            wx.MessageBox("An end marker cannot be set without a start marker.", "Validation Error", wx.OK | wx.ICON_ERROR)
            return
        
        if self.start_original_idx != -1 and self.end_original_idx != -1:
            if self.end_original_idx < self.start_original_idx:
                wx.MessageBox("End marker must be after or the same as the start marker.", "Validation Error", wx.OK | wx.ICON_ERROR)
                return

        if self.start_original_idx == -1 and self.end_original_idx == -1:
            wx.MessageBox("At least a start marker must be selected.", "Validation Error", wx.OK | wx.ICON_ERROR)
            return

        self.EndModal(wx.ID_OK)

    def get_rule(self):
        # Return original indices
        return self.start_original_idx, self.end_original_idx

class ExclusionRulesManagerDialog(wx.Dialog):
    def __init__(self, parent, exclusion_manager, all_entries):
        super(ExclusionRulesManagerDialog, self).__init__(parent, title="Manage Exclusion Rules", size=(600, 400))
        self.exclusion_manager = exclusion_manager
        self.all_entries = all_entries

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        vbox.Add(wx.StaticText(panel, label="Current Exclusion Rules:"), 0, wx.ALL, 10)

        self.rules_listbox = wx.ListBox(panel, style=wx.LB_SINGLE)
        vbox.Add(self.rules_listbox, 1, wx.EXPAND | wx.ALL, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        add_btn = wx.Button(panel, label="Add...")
        remove_btn = wx.Button(panel, label="Remove")
        close_btn = wx.Button(panel, wx.ID_CANCEL, label="Close")

        btn_sizer.Add(add_btn, 0, wx.ALL, 5)
        btn_sizer.Add(remove_btn, 0, wx.ALL, 5)
        btn_sizer.Add(close_btn, 0, wx.ALL, 5)

        vbox.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        panel.SetSizer(vbox)

        self.populate_rules_list()

        add_btn.Bind(wx.EVT_BUTTON, self.on_add_rule)
        remove_btn.Bind(wx.EVT_BUTTON, self.on_remove_rule)
        close_btn.Bind(wx.EVT_BUTTON, self.on_close)

    def populate_rules_list(self):
        self.rules_listbox.Clear()
        all_entries_msgids = [entry['msgid'] for entry in self.all_entries]
        for rule_str in self.exclusion_manager.get_rules_for_display(all_entries_msgids):
            self.rules_listbox.Append(rule_str)

    def on_add_rule(self, event):
        with AddExclusionRuleDialog(self, self.all_entries, self.exclusion_manager) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                start_idx, end_idx = dialog.get_rule()
                # The validation is now handled within AddExclusionRuleDialog's on_ok method.
                # We just need to check if a rule was successfully selected (start_idx is not -1).
                if start_idx != -1: # A start marker is always required for a valid rule
                    self.exclusion_manager.add_rule(start_idx, end_idx)
                    self.populate_rules_list()

    def on_remove_rule(self, event):
        selection = self.rules_listbox.GetSelection()
        if selection != wx.NOT_FOUND:
            if wx.MessageBox("Are you sure you want to remove this rule?", "Confirm",
                             wx.YES_NO | wx.ICON_QUESTION) == wx.YES: # Use wx.YES for explicit check
                self.exclusion_manager.remove_rule(selection)
                self.populate_rules_list()
        else:
            wx.MessageBox("Please select a rule to remove.", "No Selection", wx.OK | wx.ICON_INFORMATION)

    def on_close(self, event):
        self.EndModal(wx.ID_CANCEL)