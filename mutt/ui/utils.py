import re

import wx

_WORD_BEFORE = re.compile(r'\S+\s*$|\s+$')


def word_delete_start(text):
    """Where Ctrl+Backspace should cut to: start of the word (plus trailing
    whitespace) at the end of `text`. Returns len(text) when there is nothing
    to delete."""
    match = _WORD_BEFORE.search(text)
    return match.start() if match else len(text)


def on_ctrl_backspace(event):
    """EVT_CHAR_HOOK handler: make Ctrl+Backspace delete the previous word.

    wxMSW passes Ctrl+Backspace straight to the native edit control, which
    inserts a literal 0x7F instead of deleting anything. Bind this on a frame
    or dialog and every text box inside it behaves.
    """
    ctrl = wx.Window.FindFocus()
    if (event.GetKeyCode() != wx.WXK_BACK
            or not event.ControlDown() or event.AltDown() or event.ShiftDown()
            or not isinstance(ctrl, wx.TextCtrl) or not ctrl.IsEditable()):
        event.Skip()
        return
    start, end = ctrl.GetSelection()
    if start != end:
        ctrl.Remove(start, end)
        return
    cut = word_delete_start(ctrl.GetRange(0, start))
    if cut < start:
        ctrl.Remove(cut, start)


def safe_set_descriptive_text(control, text):
    """Safely set descriptive text on a control, checking if the method exists."""
    if hasattr(control, 'SetDescriptiveText'):
        control.SetDescriptiveText(text)
    elif hasattr(control, 'SetToolTip'):
        control.SetToolTip(text)