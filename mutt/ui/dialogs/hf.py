import wx
import threading
import os
# Optional Hugging Face engine (may be unavailable if dependencies are missing)
try:
    from mutt.engines import hf_engine
except Exception:
    hf_engine = None

class HuggingFacePanel(wx.Dialog):
    """
    Minimal Hugging Face model manager panel.

    Features:
    - Search Hub for translation models (best-effort using HFModelManager.search_translation_models)
    - Download a selected model into local cache (snapshot_download via HFModelManager.download_model)
    - List cached models and allow selecting one as "active" (returns selected_model_id & selected_device)
    This is intentionally lightweight for an initial interactable implementation.
    """
    def __init__(self, parent):
        super(HuggingFacePanel, self).__init__(parent, title="Hugging Face Models", size=(800, 520))
        self.parent = parent
        self.hf_available = bool(hf_engine and getattr(hf_engine, "HF_AVAILABLE", False))
        self.manager = hf_engine.HFModelManager(cache_dir=os.path.join("models", "hf_cache")) if self.hf_available else None
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        top_sizer.Add(wx.StaticText(panel, label="Search Hub:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.search_ctrl = wx.SearchCtrl(panel, style=wx.TE_PROCESS_ENTER)
        top_sizer.Add(self.search_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        self.search_btn = wx.Button(panel, label="Search")
        top_sizer.Add(self.search_btn, 0, wx.ALL, 5)

        # Quick model-id downloader for advanced users (also useful for exact-match models like opus-mt)
        top_sizer.Add(wx.StaticText(panel, label="Model ID:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        self.model_id_text = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.model_id_text.SetMinSize((240, -1))
        top_sizer.Add(self.model_id_text, 0, wx.ALL | wx.EXPAND, 5)
        self.download_id_btn = wx.Button(panel, label="Download by ID")
        top_sizer.Add(self.download_id_btn, 0, wx.ALL, 5)

        main_sizer.Add(top_sizer, 0, wx.EXPAND | wx.ALL, 5)

        split = wx.SplitterWindow(panel)
        left = wx.Panel(split)
        right = wx.Panel(split)

        left_sizer = wx.BoxSizer(wx.VERTICAL)
        left_sizer.Add(wx.StaticText(left, label="Search Results (model id)"), 0, wx.ALL, 5)
        self.results_list = wx.ListBox(left)
        left_sizer.Add(self.results_list, 1, wx.EXPAND | wx.ALL, 5)
        left_sizer.Add(wx.Button(left, label="Download Selected"), 0, wx.ALL | wx.ALIGN_RIGHT, 5)
        left.SetSizer(left_sizer)

        right_sizer = wx.BoxSizer(wx.VERTICAL)
        right_sizer.Add(wx.StaticText(right, label="Installed / Cached Models"), 0, wx.ALL, 5)
        self.installed_list = wx.ListBox(right)
        right_sizer.Add(self.installed_list, 1, wx.EXPAND | wx.ALL, 5)
        device_label = wx.StaticText(right, label="Device:")
        self.device_choice = wx.ComboBox(right, choices=["cpu", "cuda"], style=wx.CB_READONLY)
        current_device = self.parent.config.get("providers", {}).get("HuggingFace", {}).get("device", "cpu")
        self.device_choice.SetValue(current_device if current_device in ("cpu", "cuda") else "cpu")
        set_btn = wx.Button(right, label="Set Active Model")
        right_sizer.Add(device_label, 0, wx.ALL, 5)
        right_sizer.Add(self.device_choice, 0, wx.ALL | wx.EXPAND, 5)
        right_sizer.Add(set_btn, 0, wx.ALL | wx.ALIGN_RIGHT, 5)
        right.SetSizer(right_sizer)

        split.SplitVertically(left, right, sashPosition=460)
        main_sizer.Add(split, 1, wx.EXPAND | wx.ALL, 5)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="Close")
        btn_sizer.Add(cancel_btn, 0, wx.ALL, 5)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        panel.SetSizer(main_sizer)
        panel.Layout()

        # State
        self.search_results = []
        self.selected_model_id = None
        self.selected_device = self.device_choice.GetValue()

        # Bind events
        self.search_btn.Bind(wx.EVT_BUTTON, self.on_search)
        self.results_list.Bind(wx.EVT_LISTBOX, self.on_result_selected)
        self.installed_list.Bind(wx.EVT_LISTBOX, self.on_installed_selected)
        left.FindWindowByLabel("Download Selected").Bind(wx.EVT_BUTTON, self.on_download_selected)
        set_btn.Bind(wx.EVT_BUTTON, self.on_set_active)
        cancel_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CANCEL))

        # Populate installed models list
        wx.CallAfter(self._populate_installed)

    def _populate_installed(self):
        self.installed_list.Clear()
        if not self.hf_available:
            self.installed_list.Append("Hugging Face dependencies not installed.")
            return
        try:
            cached = self.manager.list_cached_models()
            for c in cached:
                self.installed_list.Append(c)
        except Exception as e:
            self.installed_list.Append(f"Error listing cache: {e}")

    def on_search(self, event):
        query = self.search_ctrl.GetValue().strip()
        self.results_list.Clear()
        if not self.hf_available:
            wx.MessageBox("Hugging Face dependencies not available.", "Error", wx.OK | wx.ICON_ERROR)
            return

        def work():
            try:
                hits = self.manager.search_translation_models(query=query, limit=50)
                self.search_results = hits
                wx.CallAfter(self._populate_results)
            except Exception as e:
                wx.CallAfter(wx.MessageBox, f"Search failed: {e}", "Error", wx.OK | wx.ICON_ERROR)

        threading.Thread(target=work, daemon=True).start()

    def _populate_results(self):
        self.results_list.Clear()
        for h in self.search_results:
            self.results_list.Append(h)

    def on_result_selected(self, event):
        sel = self.results_list.GetSelection()
        if sel != wx.NOT_FOUND:
            self.selected_from_search = self.search_results[sel]

    def on_installed_selected(self, event):
        sel = self.installed_list.GetSelection()
        if sel != wx.NOT_FOUND:
            self.selected_model_id = self.installed_list.GetString(sel)

    def on_download_selected(self, event):
        sel = self.results_list.GetSelection()
        if sel == wx.NOT_FOUND:
            wx.MessageBox("Please select a model to download.", "Info", wx.OK | wx.ICON_INFORMATION)
            return
        model_id = self.search_results[sel]
        dlg = wx.MessageDialog(self, f"Download and cache model '{model_id}'? This may take significant disk space.", "Confirm", wx.YES_NO | wx.ICON_QUESTION)
        if dlg.ShowModal() != wx.ID_YES:
            return

        def work():
            try:
                wx.CallAfter(wx.BeginBusyCursor)
                path = self.manager.download_model(model_id)
                wx.CallAfter(wx.EndBusyCursor)
                wx.CallAfter(wx.MessageBox, f"Downloaded to {path}", "Success", wx.OK | wx.ICON_INFORMATION)
                wx.CallAfter(self._populate_installed)
            except Exception as e:
                wx.CallAfter(wx.EndBusyCursor)
                wx.CallAfter(wx.MessageBox, f"Download failed: {e}", "Error", wx.OK | wx.ICON_ERROR)

        threading.Thread(target=work, daemon=True).start()

    def on_download_by_id(self, event):
        """
        Download a model by explicit Hugging Face model id entered by the user.
        This is a safer, explicit path for models not found via search (e.g., opus-mt-*).
        """
        model_id = self.model_id_text.GetValue().strip()
        if not model_id:
            wx.MessageBox("Please enter a model id (e.g., 'Helsinki-NLP/opus-mt-en-tr')", "Info", wx.OK | wx.ICON_INFORMATION)
            return

        dlg = wx.MessageDialog(self, f"Download and cache model '{model_id}'? This may take significant disk space.", "Confirm", wx.YES_NO | wx.ICON_QUESTION)
        if dlg.ShowModal() != wx.ID_YES:
            return

        def work():
            try:
                wx.CallAfter(wx.BeginBusyCursor)
                # For explicit-by-id downloads fetch full weights to ensure runnable model.
                # Pass allow_patterns=None to the manager to request full snapshot (manager will attempt best-effort).
                path = self.manager.download_model(model_id, allow_patterns=None)
                wx.CallAfter(wx.EndBusyCursor)
                wx.CallAfter(wx.MessageBox, f"Downloaded to {path}", "Success", wx.OK | wx.ICON_INFORMATION)
                wx.CallAfter(self._populate_installed)
            except Exception as e:
                wx.CallAfter(wx.EndBusyCursor)
                wx.CallAfter(wx.MessageBox, f"Download failed: {e}", "Error", wx.OK | wx.ICON_ERROR)

        threading.Thread(target=work, daemon=True).start()

    def on_set_active(self, event):
        # If a cached model is selected use it, otherwise if a searched model is selected and cached then use it.
        sel = self.installed_list.GetSelection()
        if sel != wx.NOT_FOUND:
            model_id = self.installed_list.GetString(sel)
        else:
            # fallback to last searched selection
            sel2 = getattr(self, "selected_from_search", None)
            model_id = sel2 if sel2 else None

        if not model_id:
            wx.MessageBox("Please select an installed/cached model to set as active.", "Info", wx.OK | wx.ICON_INFORMATION)
            return

        self.selected_model_id = model_id
        self.selected_device = self.device_choice.GetValue()
        # Persist choice into parent's config immediately for convenience
        self.parent.config.setdefault("providers", {})["HuggingFace"] = {"api_key": "", "api_model": model_id, "device": self.selected_device}
        wx.MessageBox(f"Set active model to: {model_id} (device: {self.selected_device})", "Success", wx.OK | wx.ICON_INFORMATION)
        self.EndModal(wx.ID_OK)