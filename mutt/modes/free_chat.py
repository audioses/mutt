# mutt/modes/free_chat.py

import wx
from .base_mode import BaseMode

class FreeChatMode(BaseMode):
    """
    Mode for a free-form chat with the AI.
    """
    def __init__(self, app_context, aiserver):
        super().__init__(app_context, aiserver)
        self.name = "Free Chat"
        self.description = "Open-ended chat with the AI for any questions or tasks."
        self.chat_history = []

    def get_ui_layout(self, parent):
        """
        Returns the UI layout for this mode.
        """
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Simple chat input
        self.chat_input = wx.TextCtrl(parent, style=wx.TE_PROCESS_ENTER)
        sizer.Add(self.chat_input, 0, wx.EXPAND | wx.ALL, 5)
        
        return sizer

    def execute(self, data):
        """
        Executes the mode's logic.
        """
        user_message = self.chat_input.GetValue()
        if not user_message:
            return "Please enter a message."

        # Add user message to history
        self.chat_history.append({"role": "user", "content": user_message})
        
        # Prepare a simplified history for the prompt
        prompt_history = "\n".join([f"{msg['role']}: {msg['content']}" for msg in self.chat_history])
        prompt = f"Continue the conversation.\n{prompt_history}\nassistant:"

        try:
            response, _ = self.aiserver._execute_single_prompt(prompt)
            # Add assistant response to history
            self.chat_history.append({"role": "assistant", "content": response})
            self.chat_input.Clear()
            return response
        except Exception as e:
            # Remove the user message if the call fails
            self.chat_history.pop()
            return f"Error in chat: {e}"