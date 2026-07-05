# mutt/modes/check_errors.py

import wx
from .base_mode import BaseMode

class CheckErrorsMode(BaseMode):
    """
    Mode to check for grammatical errors in the target text.
    """
    def __init__(self, app_context, aiserver):
        super().__init__(app_context, aiserver)
        self.name = "Check for Errors"
        self.description = "Scans the target text for grammatical mistakes, typos, and inconsistencies."

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
        target_text = data.get("target_text", "")

        if not target_text:
            return "No target text to check."

        prompt = f"Please check the following text for any grammatical errors, typos, or inconsistencies. If you find any, provide a corrected version and a brief explanation of the changes. If there are no errors, just say so.\n\nText to check: '{target_text}'"
        
        try:
            response, _ = self.aiserver._execute_single_prompt(prompt)
            return response
        except Exception as e:
            return f"Error checking for errors: {e}"