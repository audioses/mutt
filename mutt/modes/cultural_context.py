# mutt/modes/cultural_context.py

import wx
from .base_mode import BaseMode

class CulturalContextMode(BaseMode):
    """
    Mode to get cultural context for a selected text.
    """
    def __init__(self, app_context, aiserver):
        super().__init__(app_context, aiserver)
        self.name = "Cultural Context"
        self.description = "Provides cultural context, idioms, or sensitive topics related to the selected text."

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
        selected_text = data.get("selected_text", "")

        if not selected_text:
            return "No text selected."

        prompt = f"What is the cultural context or significance of the phrase '{selected_text}'? Are there any related idioms or sensitive topics to be aware of?"
        
        try:
            response, _ = self.aiserver._execute_single_prompt(prompt)
            return response
        except Exception as e:
            return f"Error getting cultural context: {e}"