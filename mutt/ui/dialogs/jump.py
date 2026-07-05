import wx

# NEW: Dialog for jumping to a specific entry number
class JumpDialog(wx.Dialog):
    def __init__(self, parent, max_entry):
        super(JumpDialog, self).__init__(parent, title="Jump to Entry", size=(300, 150))
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(wx.StaticText(panel, label=f"Enter entry number (1 - {max_entry}):"), 0, wx.ALL, 10)
        self.entry_spin = wx.SpinCtrl(panel, min=1, max=max_entry, initial=1)
        sizer.Add(self.entry_spin, 0, wx.EXPAND|wx.ALL, 10)

        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER|wx.ALL, 10)

        panel.SetSizerAndFit(sizer)

    def get_value(self):
        return self.entry_spin.GetValue()