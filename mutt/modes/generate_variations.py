# mutt/modes/generate_variations.py

import wx
from .base_mode import BaseMode

class GenerateVariationsMode(BaseMode):
    """
    Mode to generate variations of a given text.
    """
    def __init__(self, app_context, aiserver):
        super().__init__(app_context, aiserver)
        self.name = "Generate Variations"
        self.description = "Generates alternative phrasings and stylistic variations of the selected text."

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

        prompt = f"Generate a few stylistic variations of the following text: '{selected_text}'"
        
        try:
            response, _ = self.aiserver._execute_single_prompt(prompt)
            return response
        except Exception as e:
            return f"Error generating variations: {e}"