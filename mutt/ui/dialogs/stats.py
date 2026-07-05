import wx

from mutt.logic.stats import compute_translation_stats, format_stats_report


class TranslationStatsDialog(wx.Dialog):
    """Read-only, keyboard-friendly summary of translation progress."""

    def __init__(self, parent, all_entries, exclusion_manager=None, ignore_rules=None):
        super().__init__(parent, title="Translation Statistics", size=(440, 360))

        stats = compute_translation_stats(all_entries, exclusion_manager, ignore_rules)
        report = format_stats_report(stats)

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # A read-only multiline TextCtrl (not StaticText) so screen-reader
        # users can navigate and copy the figures.
        text = wx.TextCtrl(
            panel,
            value=report,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP,
        )
        text.SetFont(wx.Font(wx.FontInfo(10).Family(wx.FONTFAMILY_TELETYPE)))
        vbox.Add(text, 1, wx.EXPAND | wx.ALL, 10)

        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK)
        ok_btn.SetDefault()
        btn_sizer.AddButton(ok_btn)
        btn_sizer.Realize()
        vbox.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        panel.SetSizer(vbox)
        text.SetFocus()
