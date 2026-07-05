# mutt/modes/get_etymology.py

import wx
from .base_mode import BaseMode

class GetEtymologyMode(BaseMode):
    """
    Mode to get the etymology of a selected word.
    """
    def __init__(self, app_context, aiserver):
        super().__init__(app_context, aiserver)
        self.name = "Get Etymology"
        self.description = "Provides the etymology and origin of a selected word."

    def get_ui_layout(self, parent):
        """
        Returns the UI layout for this mode.
        """
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Add a text input for the word to get etymology for
        label = wx.StaticText(parent, label="Enter word:")
        sizer.Add(label, 0, wx.ALL, 5)
        
        self.word_input = wx.TextCtrl(parent)
        sizer.Add(self.word_input, 0, wx.EXPAND | wx.ALL, 5)
        
        return sizer

    def execute(self, data):
        """
        Executes the mode's logic.
        """
        # Get the word from the UI input field
        word = ""
        if hasattr(self, 'word_input'):
            word = self.word_input.GetValue().strip()
        
        if not word:
            return "Please enter a word."

        prompt = f"What is the etymology of the word '{word}'?"
        
        try:
            response, _ = self.aiserver._execute_single_prompt(prompt)
            return response
        except Exception as e:
            return f"Error getting etymology: {e}"
