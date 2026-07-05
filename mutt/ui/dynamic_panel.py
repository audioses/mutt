# mutt/ui/dynamic_panel.py

import wx

def create_dynamic_panel(parent, ui_config, data_store):
    """
    Creates a dynamic panel based on UI configuration from YAML mode files.
    
    Args:
        parent: The parent wx.Panel or wx.Window
        ui_config: List of UI element configurations from YAML
        data_store: Dictionary to store UI control references
        
    Returns:
        wx.Panel: The panel with dynamically created UI elements
    """
    panel = wx.Panel(parent)
    sizer = wx.BoxSizer(wx.VERTICAL)
    
    for element in ui_config:
        element_id = element.get('id')
        element_type = element.get('type')
        label = element.get('label', '')
        
        if element_type == 'multiline':
            # Create label
            if label:
                sizer.Add(wx.StaticText(panel, label=label), 0, wx.ALL, 5)
            # Create multiline text control
            ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_WORDWRAP)
            sizer.Add(ctrl, 1, wx.ALL | wx.EXPAND, 5)
            data_store[element_id] = ctrl
            
        elif element_type == 'multiline-readonly':
            # Create label
            if label:
                sizer.Add(wx.StaticText(panel, label=label), 0, wx.ALL, 5)
            # Create readonly multiline text control
            ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP)
            sizer.Add(ctrl, 1, wx.ALL | wx.EXPAND, 5)
            data_store[element_id] = ctrl
            
        elif element_type == 'text':
            # Create label
            if label:
                sizer.Add(wx.StaticText(panel, label=label), 0, wx.ALL, 5)
            # Create single line text control
            ctrl = wx.TextCtrl(panel)
            sizer.Add(ctrl, 0, wx.ALL | wx.EXPAND, 5)
            data_store[element_id] = ctrl
            
        elif element_type == 'dropdown':
            # Create label
            if label:
                sizer.Add(wx.StaticText(panel, label=label), 0, wx.ALL, 5)
            # Create dropdown with choices
            choices = element.get('choices', [])
            ctrl = wx.ComboBox(panel, choices=choices, style=wx.CB_DROPDOWN)
            if choices:
                ctrl.SetSelection(0)
            sizer.Add(ctrl, 0, wx.ALL | wx.EXPAND, 5)
            data_store[element_id] = ctrl
            
    panel.SetSizer(sizer)
    return panel

def get_data_from_controls(data_store):
    """
    Extracts data from UI controls in the data store.
    
    Args:
        data_store: Dictionary containing UI control references
        
    Returns:
        dict: Dictionary with control IDs as keys and their values as values
    """
    data = {}
    for key, ctrl in data_store.items():
        if isinstance(ctrl, wx.TextCtrl):
            data[key] = ctrl.GetValue()
        elif isinstance(ctrl, wx.ComboBox):
            data[key] = ctrl.GetValue()
    return data

def set_data_to_controls(data_store, data):
    """
    Sets data to UI controls in the data store.
    
    Args:
        data_store: Dictionary containing UI control references
        data: Dictionary with control IDs as keys and their values as values
    """
    for key, value in data.items():
        if key in data_store:
            ctrl = data_store[key]
            if isinstance(ctrl, wx.TextCtrl):
                ctrl.SetValue(str(value))
            elif isinstance(ctrl, wx.ComboBox):
                ctrl.SetValue(str(value))