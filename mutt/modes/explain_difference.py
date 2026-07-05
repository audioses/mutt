# mutt/modes/explain_difference.py

import wx
from .base_mode import BaseMode

class ExplainDifferenceMode(BaseMode):
    """
    Mode to explain the difference between the source text and its translation.
    """
    def __init__(self, app_context, aiserver):
        super().__init__(app_context, aiserver)
        self.name = "Explain Difference"
        self.description = "Explains the nuance and grammatical differences between the source and target text."

    def get_ui_layout(self, parent):
        """
        Returns the UI layout for this mode.
        """
        sizer = wx.BoxSizer(wx.VERTICAL)
        # No specific UI needed for this mode, as it operates on selected text
        return sizer

    def execute(self, data):
        """
        Executes the mode's logic.
        """
        source_text = data.get("source_text", "")
        target_text = data.get("target_text", "")

        if not source_text or not target_text:
            return "Source or target text is missing."

        prompt = f"Explain the grammatical and nuanced differences between the following two texts. Source: '{source_text}' Target: '{target_text}'"
        
        try:
            response, _ = self.aiserver._execute_single_prompt(prompt)
            return response
        except Exception as e:
            return f"Error explaining difference: {e}"
