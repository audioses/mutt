# mutt/modes/base_mode.py

import abc

class BaseMode(abc.ABC):
    """
    Abstract base class for all modes in the Translator's Toolbox.
    """
    def __init__(self, app_context, aiserver):
        self.app_context = app_context
        self.aiserver = aiserver
        self.name = "Unnamed Mode"
        self.description = "No description provided"
        
    @abc.abstractmethod
    def get_ui_layout(self, parent):
        """
        Returns the UI layout for this mode.
        
        Args:
            parent: The parent wx.Panel or wx.Window
            
        Returns:
            wx.Sizer: The sizer containing the UI elements
        """
        pass
        
    @abc.abstractmethod
    def execute(self, data):
        """
        Executes the mode's logic.
        
        Args:
            data (dict): The data collected from the UI
            
        Returns:
            str: The result of the execution
        """
        pass