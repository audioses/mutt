"""What the app says when the Translate button has nothing to work on.

Importing ``mutt.app`` here is half the point: it is the largest module in
the project and no other test touched it, so a syntax error in it sailed
past the whole suite.
"""
import pytest

wx = pytest.importorskip("wx")

from mutt.app import MainFrame


class _Radio:
    def __init__(self, selection):
        self._selection = selection

    def GetSelection(self):
        return self._selection


class _Frame:
    """Just enough of the frame for the message builder, no wx window."""

    def __init__(self, entries, mode):
        self.all_po_entries = entries
        self.translation_mode_radio = _Radio(mode)


def _reason(entries, mode=0):
    return MainFrame._empty_selection_reason(_Frame(entries, mode))


def test_no_file_loaded_points_at_the_open_command():
    assert "File > Open" in _reason([])


def test_untranslated_mode_says_the_file_is_done_and_offers_translate_all():
    msg = _reason([{"msgid": "a", "msgstr": "A"}] * 9261)
    assert "9261" in msg
    assert "Translate all" in msg


def test_translate_all_mode_blames_the_rules_not_the_translations():
    msg = _reason([{"msgid": "a", "msgstr": ""}] * 12, mode=1)
    assert "exclusion rules" in msg
    assert "Translate all" not in msg  # that is already the active mode
