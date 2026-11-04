import wx

from ..utils import on_ctrl_backspace

class PromptManagerDialog(wx.Dialog):
    def __init__(self, parent, prompts):
        super(PromptManagerDialog, self).__init__(parent, title="Prompt Manager", size=(750, 550))
        # ... (rest of the class is unchanged)
        self.prompts = [p.copy() for p in prompts]
        panel = wx.Panel(self); main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        left_sizer = wx.BoxSizer(wx.VERTICAL); left_sizer.Add(wx.StaticText(panel, label="Prompts:"), 0, wx.ALL, 5)
        self.prompt_list = wx.ListBox(panel, style=wx.LB_SINGLE); left_sizer.Add(self.prompt_list, 1, wx.EXPAND|wx.ALL, 5); main_sizer.Add(left_sizer, 1, wx.EXPAND)
        right_sizer = wx.BoxSizer(wx.VERTICAL); right_sizer.Add(wx.StaticText(panel, label="Prompt Name:"), 0, wx.ALL, 5)
        self.prompt_name = wx.TextCtrl(panel); right_sizer.Add(self.prompt_name, 0, wx.EXPAND|wx.ALL, 5)
        right_sizer.Add(wx.StaticText(panel, label="Prompt Content:"), 0, wx.ALL, 5); self.prompt_content = wx.TextCtrl(panel, style=wx.TE_MULTILINE); right_sizer.Add(self.prompt_content, 1, wx.EXPAND|wx.ALL, 5)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL); self.new_btn = wx.Button(panel, label="New"); self.save_btn = wx.Button(panel, label="Save Changes"); self.delete_btn = wx.Button(panel, label="Delete")
        btn_sizer.Add(self.new_btn, 0, wx.ALL, 5); btn_sizer.Add(self.save_btn, 0, wx.ALL, 5); btn_sizer.Add(self.delete_btn, 0, wx.ALL, 5); right_sizer.Add(btn_sizer, 0, wx.ALIGN_LEFT); main_sizer.Add(right_sizer, 2, wx.EXPAND|wx.LEFT, 10)
        ok_cancel_sizer = wx.StdDialogButtonSizer(); ok_button = wx.Button(panel, wx.ID_OK); cancel_button = wx.Button(panel, wx.ID_CANCEL); ok_cancel_sizer.AddButton(ok_button); ok_cancel_sizer.AddButton(cancel_button); ok_cancel_sizer.Realize()
        top_sizer = wx.BoxSizer(wx.VERTICAL); top_sizer.Add(main_sizer, 1, wx.EXPAND|wx.ALL, 10); top_sizer.Add(ok_cancel_sizer, 0, wx.ALIGN_CENTER|wx.ALL, 10)
        panel.SetSizer(top_sizer); self.populate_list(); self.clear_editor(); self.prompt_list.Bind(wx.EVT_LISTBOX, self.on_select_prompt); self.new_btn.Bind(wx.EVT_BUTTON, self.on_new); self.save_btn.Bind(wx.EVT_BUTTON, self.on_save); self.delete_btn.Bind(wx.EVT_BUTTON, self.on_delete); self.Bind(wx.EVT_BUTTON, self.on_ok, ok_button); self.Bind(wx.EVT_CHAR_HOOK, on_ctrl_backspace)
    def populate_list(self): self.prompt_list.Clear(); [self.prompt_list.Append(p["name"]) for p in self.prompts]
    def on_select_prompt(self, event):
        idx = self.prompt_list.GetSelection(); prompt_data = self.prompts[idx]; self.prompt_name.SetValue(prompt_data["name"]); self.prompt_content.SetValue(prompt_data["prompt"])
        is_system = prompt_data.get("system", False); self.prompt_name.Enable(not is_system); self.delete_btn.Enable(not is_system)
    def on_new(self, event): self.clear_editor()
    def on_save(self, event):
        name = self.prompt_name.GetValue().strip(); content = self.prompt_content.GetValue().strip()
        if not name or not content: wx.MessageBox("Name and content cannot be empty.", "Error"); return
        idx = self.prompt_list.GetSelection()
        if idx != wx.NOT_FOUND: self.prompts[idx]["name"] = name; self.prompts[idx]["prompt"] = content
        else: self.prompts.append({"name": name, "prompt": content, "system": False})
        self.populate_list(); self.prompt_list.SetStringSelection(name); self.on_select_prompt(None)
    def on_delete(self, event):
        idx = self.prompt_list.GetSelection(); del self.prompts[idx]; self.populate_list(); self.clear_editor()
    def clear_editor(self):
        self.prompt_list.SetSelection(wx.NOT_FOUND); self.prompt_name.SetValue(""); self.prompt_content.SetValue(""); self.prompt_name.Enable(True); self.delete_btn.Enable(True)
    def on_ok(self, event): self.EndModal(wx.ID_OK)
    def get_prompts(self): return self.prompts