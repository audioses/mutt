import wx
import threading
import sys
from mutt.ui.utils import safe_set_descriptive_text
from local_model_manager import LocalModelManager
from mutt.ui.dialogs.model_download import ModelDownloadDialog

class LocalModelDialog(wx.Dialog):
    # ... (This class is unchanged)
    def __init__(self, parent):
        super(LocalModelDialog, self).__init__(parent, title="Local Model Manager", size=(800, 600))
        self.model_manager = LocalModelManager(); self.available_models = []
        panel = wx.Panel(self); main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.tab_radio = wx.RadioBox(panel, label="View", choices=["Find New Models", "Manage Installed Models"], majorDimension=2, style=wx.RA_SPECIFY_COLS)
        main_sizer.Add(self.tab_radio, 0, wx.ALL | wx.EXPAND, 5)
        self.content_panel = wx.Panel(panel); main_sizer.Add(self.content_panel, 1, wx.EXPAND | wx.ALL, 5)
        panel.SetSizer(main_sizer); self.tab_radio.Bind(wx.EVT_RADIOBOX, self.on_tab_changed)
        self.current_tab = 0
        self._create_find_interface()
        # The following line caused an AttributeError because installed_models_list is not yet created.
        # self.load_config()
        # Instead, load_config will be called when the manage interface is created.
    def on_tab_changed(self, event):
        new_tab = self.tab_radio.GetSelection()
        if new_tab != self.current_tab:
            self.current_tab = new_tab
            self._create_find_interface() if new_tab == 0 else self._create_manage_interface()
    def _create_find_interface(self):
        """Create the find new models interface"""
        self.content_panel.DestroyChildren()
        
        find_sizer = wx.BoxSizer(wx.VERTICAL)
        
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_label = wx.StaticText(self.content_panel, label="Search for GGUF Models:")
        search_label.SetName("SearchLabel")
        search_sizer.Add(search_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.search_ctrl = wx.SearchCtrl(self.content_panel, style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.SetName("SearchInput")
        safe_set_descriptive_text(self.search_ctrl, "e.g., Gemma, Llama, Mistral")
        # Accessibility enhancement: set accessible label for the input field
        try:
            # Set the label as the accessible name for the input field
            self.search_ctrl.SetName("Search for GGUF Models input")
            # Set tooltip for accessibility
            safe_set_descriptive_text(self.search_ctrl, "Search for GGUF Models")
        except Exception as e:
            print(f"[A11Y] Failed to set accessibility properties: {e}", file=sys.stderr)
        search_sizer.Add(self.search_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        self.search_btn = wx.Button(self.content_panel, label="Search")
        self.search_btn.SetName("SearchButton")
        search_sizer.Add(self.search_btn, 0, wx.ALL, 5)
        find_sizer.Add(search_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        self.search_results = wx.ListCtrl(self.content_panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.search_results.SetName("AvailableModelsList")
        self.search_results.InsertColumn(0, "Model ID", width=350)
        self.search_results.InsertColumn(1, "Params", width=70)
        self.search_results.InsertColumn(2, "Quantization", width=100)
        self.search_results.InsertColumn(3, "Status", width=100)
        self.search_results.InsertColumn(4, "Downloads", width=80)
        self.search_results.InsertColumn(5, "Description", width=200)

        find_sizer.Add(self.search_results, 1, wx.EXPAND | wx.TOP, 5)
        
        # Quant selection controls (preferred quant) - initially only Auto, will be populated per-repo
        quant_sizer = wx.BoxSizer(wx.HORIZONTAL)
        quant_label = wx.StaticText(self.content_panel, label="Preferred quant:")
        quant_sizer.Add(quant_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        # Start with only Auto and disable until a model is selected and quants are fetched
        self.quant_choice = wx.ComboBox(self.content_panel, choices=["Auto"], style=wx.CB_READONLY)
        self.quant_choice.SetValue("Auto")
        self.quant_choice.Disable()
        quant_sizer.Add(self.quant_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        find_sizer.Add(quant_sizer, 0, wx.ALIGN_LEFT | wx.ALL, 5)

        # Create a horizontal sizer for the buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.download_button = wx.Button(self.content_panel, label="Download Selected Model")
        self.download_button.SetName("DownloadModelButton")
        self.download_button.Bind(wx.EVT_BUTTON, self.on_download)
        self.download_button.Disable()
        button_sizer.Add(self.download_button, 0, wx.ALL, 5) # Use wx.ALL for consistent spacing

        self.open_browser_button = wx.Button(self.content_panel, label="Open in Browser")
        self.open_browser_button.SetName("OpenInBrowserButton")
        self.open_browser_button.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.open_browser_button.Disable()
        button_sizer.Add(self.open_browser_button, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 5) # Align with download button

        find_sizer.Add(button_sizer, 0, wx.ALIGN_RIGHT | wx.TOP, 5)

        self.content_panel.SetSizer(find_sizer)
        self.search_ctrl.Bind(wx.EVT_TEXT_ENTER, self.on_search)
        self.search_btn.Bind(wx.EVT_BUTTON, self.on_search)
        self.search_results.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_model_selected)
        self.search_results.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_model_deselected)
        self.content_panel.Layout()
    def _create_manage_interface(self):
        """Create the manage installed models interface"""
        self.content_panel.DestroyChildren()
        
        manage_sizer = wx.BoxSizer(wx.VERTICAL)
        self.installed_models_list = wx.ListCtrl(self.content_panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.installed_models_list.InsertColumn(0, "Model Name", width=250); self.installed_models_list.InsertColumn(1, "Date Installed", width=150); self.installed_models_list.InsertColumn(2, "Size (MB)", width=100); self.installed_models_list.InsertColumn(3, "File Path", width=300)
        manage_sizer.Add(self.installed_models_list, 1, wx.EXPAND)
        self.uninstall_button = wx.Button(self.content_panel, label="Uninstall Selected Model"); self.uninstall_button.Bind(wx.EVT_BUTTON, self.on_uninstall); self.uninstall_button.Disable()
        manage_sizer.Add(self.uninstall_button, 0, wx.ALIGN_RIGHT | wx.TOP, 5); self.content_panel.SetSizer(manage_sizer); self.installed_models_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_installed_model_selected); self.load_config(); self.content_panel.Layout()
    def _populate_installed_models(self):
        self.installed_models_list.DeleteAllItems()
        for i, model in enumerate(self.model_manager.get_installed_models()):
            index = self.installed_models_list.InsertItem(i, model["name"]); self.installed_models_list.SetItem(index, 1, model.get("installed_date", "N/A")); self.installed_models_list.SetItem(index, 2, model.get("size", "N/A")); self.installed_models_list.SetItem(index, 3, model.get("path", "N/A")); self.installed_models_list.SetItemData(index, i)
    def on_search(self, event):
        query = self.search_ctrl.GetValue(); wx.CallAfter(wx.BeginBusyCursor); threading.Thread(target=self.search_and_update_list, args=(query,)).start()
    def search_and_update_list(self, query):
        self.available_models = self.model_manager.get_available_models(query); wx.CallAfter(self.populate_search_results); wx.CallAfter(wx.EndBusyCursor)
    def populate_search_results(self):
        self.search_results.DeleteAllItems()
        for i, model in enumerate(self.available_models):
            status = "Installed" if self.model_manager.is_model_installed(model["id"]) else "Available"; self.search_results.InsertItem(i, model["name"]); self.search_results.SetItem(i, 1, model.get("params", "N/A")); self.search_results.SetItem(i, 2, model.get("quantization", "N/A")); self.search_results.SetItem(i, 3, status); self.search_results.SetItem(i, 4, str(model.get('downloads', 'N/A'))); self.search_results.SetItem(i, 5, model.get('description', 'N/A')); self.search_results.SetItemData(i, i)
    def on_model_selected(self, event):
        self.download_button.Enable()
        self.open_browser_button.Enable()
        # When a model is selected, populate the quant_choice with actual downloadable quants from the repo
        try:
            selection = self.search_results.GetFirstSelected()
            if selection == wx.NOT_FOUND:
                return
            model = self.available_models[selection]
            model_id = model.get("id")
        except Exception:
            return

        # Disable the quant_choice while we fetch options
        if hasattr(self, 'quant_choice'):
            wx.CallAfter(self.quant_choice.Disable)
            wx.CallAfter(self.quant_choice.SetItems, ["Auto"])
            wx.CallAfter(self.quant_choice.SetValue, "Auto")
            wx.CallAfter(safe_set_descriptive_text, self.quant_choice, "Detecting available quant variants...")

        def fetch_and_populate():
            try:
                quants = self.model_manager.list_repo_gguf_quants(model_id)
                if not quants:
                    # No variants found; keep only Auto
                    wx.CallAfter(self.quant_choice.SetItems, ["Auto"])
                    wx.CallAfter(self.quant_choice.SetValue, "Auto")
                    wx.CallAfter(safe_set_descriptive_text, self.quant_choice, "No quant variants detected; downloader will pick best available.")
                    wx.CallAfter(self.quant_choice.Disable)
                else:
                    choices = ["Auto"] + quants
                    wx.CallAfter(self.quant_choice.SetItems, choices)
                    wx.CallAfter(self.quant_choice.SetValue, "Auto")
                    wx.CallAfter(self.quant_choice.Enable)
                    wx.CallAfter(safe_set_descriptive_text, self.quant_choice, "Select a quant variant detected in the repository.")
            except Exception as e:
                # On error, revert to Auto only
                wx.CallAfter(self.quant_choice.SetItems, ["Auto"])
                wx.CallAfter(self.quant_choice.SetValue, "Auto")
                wx.CallAfter(safe_set_descriptive_text, self.quant_choice, f"Error detecting variants: {e}")
                wx.CallAfter(self.quant_choice.Disable)

        threading.Thread(target=fetch_and_populate, daemon=True).start()

    def on_model_deselected(self, event):
        # Disable buttons if no item is selected
        if self.search_results.GetSelectedItemCount() == 0:
            self.download_button.Disable()
            self.open_browser_button.Disable()

    def on_installed_model_selected(self, event):
        self.uninstall_button.Enable()

    def on_open_browser(self, event):
        selection = self.search_results.GetFirstSelected()
        if selection == wx.NOT_FOUND:
            wx.MessageBox("Please select a model from the list to open in browser.", "Info", wx.OK | wx.ICON_INFORMATION)
            return
        
        model = self.available_models[selection]
        model_id = model.get("id")
        
        if model_id:
            url = f"https://huggingface.co/{model_id}"
            wx.LaunchDefaultBrowser(url)
        else:
            wx.MessageBox("Could not find model URL.", "Error", wx.OK | wx.ICON_ERROR)

    def on_download(self, event):
        selection = self.search_results.GetFirstSelected()
        if selection == wx.NOT_FOUND:
            wx.MessageBox("Please select a model from the list to download.", "Info", wx.OK | wx.ICON_INFORMATION)
            return
        
        model = self.available_models[selection]
        if self.model_manager.is_model_installed(model["id"]):
            wx.MessageBox(f"'{model['name']}' is already installed.", "Info", wx.OK | wx.ICON_INFORMATION)
            return
        
        with wx.MessageDialog(self,
                            f"You are about to download a GGUF model file from:\n\n{model['name']}\n\nThis may take a significant amount of time and disk space.",
                            "Confirm Download",
                            wx.YES_NO | wx.ICON_QUESTION) as dlg:
            if dlg.ShowModal() == wx.ID_YES:
                # Retrieve preferred quant selection from UI if available
                preferred_quant = self.quant_choice.GetValue() if hasattr(self, 'quant_choice') else "Auto"
                with ModelDownloadDialog(self, model["id"], model["name"], preferred_quant) as download_dlg:
                    # The download dialog is modal, so we wait for it to be created
                    wx.CallAfter(download_dlg.start_download)
                    download_dlg.ShowModal() # This will block until the download dialog is closed

                    # After it closes, refresh data
                    self._populate_installed_models()
                    self.populate_search_results() # Re-populates with updated "Installed" status
                        
    def on_uninstall(self, event):
        selected_index = self.installed_models_list.GetFirstSelected()
        if selected_index == -1:
            return

        # We need to get the model ID from the originally populated list
        original_index = self.installed_models_list.GetItemData(selected_index)
        model_id = self.model_manager.get_installed_models()[original_index]['id']

        if wx.MessageBox(f"Are you sure you want to uninstall {model_id}?", "Confirm Uninstall",
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION) == wx.YES:
            if self.model_manager.uninstall_model(model_id):
                wx.MessageBox(f"{model_id} has been uninstalled.", "Success", wx.OK | wx.ICON_INFORMATION)
                self._populate_installed_models()
            else:
                wx.MessageBox(f"Failed to uninstall {model_id}.", "Error", wx.OK | wx.ICON_ERROR)

    def load_config(self):
        # The manager handles config loading
        self._populate_installed_models()