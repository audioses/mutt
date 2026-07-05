import wx

def create_menu_bar(frame):
    menu_bar = wx.MenuBar()
    file_menu = wx.Menu()
    open_item = file_menu.Append(wx.ID_OPEN, "&Open Source File...\tCtrl+O")
    open_project_item = file_menu.Append(wx.ID_ANY, "Open &Project...")
    file_menu.AppendSeparator()
    save_item = file_menu.Append(wx.ID_SAVE, "&Save Final Translation\tCtrl+S")
    save_as_item = file_menu.Append(wx.ID_SAVEAS, "Save Final Translation &As...\tCtrl+Shift+S")
    save_project_item = file_menu.Append(wx.ID_ANY, "Save P&roject As...")
    file_menu.AppendSeparator()
    load_ignore_item = file_menu.Append(wx.ID_ANY, "Load &Ignore List...") # NEW: Load ignore rules
    file_menu.AppendSeparator()
    exit_item = file_menu.Append(wx.ID_EXIT, "E&xit")
    menu_bar.Append(file_menu, "&File")

    settings_menu = wx.Menu()
    api_item = settings_menu.Append(wx.ID_ANY, "&API Settings...")
    prompt_item = settings_menu.Append(wx.ID_ANY, "Manage &Prompts...")
    menu_bar.Append(settings_menu, "&Settings")

    # NEW: Tools Menu
    tools_menu = wx.Menu()
    manage_exclusion_rules_item = tools_menu.Append(wx.ID_ANY, "Manage Exclusion &Rules...")
    export_exclusion_rules_item = tools_menu.Append(wx.ID_ANY, "Export Exclusion R&ules...") # NEW: Export exclusion rules
    tools_menu.AppendSeparator()
    stats_item = tools_menu.Append(wx.ID_ANY, "Translation &Statistics...\tCtrl+T")
    menu_bar.Append(tools_menu, "&Tools")

    frame.SetMenuBar(menu_bar)

    frame.Bind(wx.EVT_MENU, frame.on_open_file, open_item)
    frame.Bind(wx.EVT_MENU, frame.on_open_project, open_project_item)
    frame.Bind(wx.EVT_MENU, frame.on_save_changes, save_item)
    frame.Bind(wx.EVT_MENU, frame.on_save_as, save_as_item)
    frame.Bind(wx.EVT_MENU, frame.on_save_project, save_project_item)
    frame.Bind(wx.EVT_MENU, frame.on_load_ignore_list, load_ignore_item) # NEW: Bind ignore list
    frame.Bind(wx.EVT_MENU, frame.on_exit, exit_item)
    frame.Bind(wx.EVT_MENU, frame.on_api_settings, api_item)
    frame.Bind(wx.EVT_MENU, frame.on_manage_prompts, prompt_item)
    frame.Bind(wx.EVT_MENU, frame.on_manage_exclusion_rules, manage_exclusion_rules_item) # NEW: Bind exclusion rules manager
    frame.Bind(wx.EVT_MENU, frame.on_export_exclusion_rules, export_exclusion_rules_item) # NEW: Bind export exclusion rules
    frame.Bind(wx.EVT_MENU, frame.on_show_statistics, stats_item)
    frame.CreateStatusBar()
