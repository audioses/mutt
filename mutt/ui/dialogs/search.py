import wx

# NEW: Non-modal dialog for searching through entries
class SearchDialog(wx.Dialog):
    def __init__(self, parent):
        super(SearchDialog, self).__init__(parent, title="Find in Entries")
        self.parent = parent # Store a reference to the MainFrame

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(wx.StaticText(panel, label="Find what:"), 0, wx.ALL, 5)
        self.search_text = wx.TextCtrl(panel)
        sizer.Add(self.search_text, 0, wx.EXPAND|wx.ALL, 5)

        self.scope_radio = wx.RadioBox(panel, label="Scope", choices=["Source Text", "Target Text", "Both"], style=wx.RA_SPECIFY_COLS)
        sizer.Add(self.scope_radio, 0, wx.EXPAND|wx.ALL, 5)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        find_prev_btn = wx.Button(panel, label="Find Previous")
        find_next_btn = wx.Button(panel, label="Find Next")
        btn_sizer.Add(find_prev_btn, 0, wx.ALL, 5)
        btn_sizer.Add(find_next_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT)

        panel.SetSizerAndFit(sizer)
        self.search_text.SetFocus()

        find_prev_btn.Bind(wx.EVT_BUTTON, self.on_find_prev)
        find_next_btn.Bind(wx.EVT_BUTTON, self.on_find_next)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        # Modeless dialogs don't get wx's built-in Escape handling.
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)

    def on_char_hook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close()
            return
        event.Skip()

    def on_find_prev(self, event):
        self.parent.find_entry(self.search_text.GetValue(), self.scope_radio.GetSelection(), forward=False)

    def on_find_next(self, event):
        self.parent.find_entry(self.search_text.GetValue(), self.scope_radio.GetSelection(), forward=True)

    def on_close(self, event):
        self.parent.search_dialog = None # Let the parent know we're gone
        self.Destroy()