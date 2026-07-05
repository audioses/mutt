import wx

def create_language_panel(frame, parent):
    lang_sizer = wx.BoxSizer(wx.HORIZONTAL)
    lang_sizer.Add(wx.StaticText(parent, label="Source:"), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
    frame.src_lang_text = wx.TextCtrl(parent, value=frame.source_language)
    lang_sizer.Add(frame.src_lang_text, 1, wx.EXPAND|wx.ALL, 5)
    lang_sizer.Add(wx.StaticText(parent, label="Target:"), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
    frame.tgt_lang_text = wx.TextCtrl(parent, value=frame.target_language)
    lang_sizer.Add(frame.tgt_lang_text, 1, wx.EXPAND|wx.ALL, 5)
    
    frame.src_lang_text.Bind(wx.EVT_TEXT, frame.on_src_lang_text_changed)
    frame.tgt_lang_text.Bind(wx.EVT_TEXT, frame.on_tgt_lang_text_changed)
    
    return lang_sizer