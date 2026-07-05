import wx
import threading
from mutt.ui.utils import safe_set_descriptive_text
from mutt.engines import argos_engine

class ArgosModelDialog(wx.Dialog):
    """
    Argos package manager dialog with package index support.

    Features:
    - Update remote Argos package index
    - Search available packages from the index
    - Download & install selected packages via Argos APIs
    - Install from local .argosmodel files
    - List installed Argos languages
    """
    def __init__(self, parent):
        super(ArgosModelDialog, self).__init__(parent, title="Argos Package Manager", size=(800, 520))
        panel = wx.Panel(self)
        self.argos_available = True
        try:
            pass
        except Exception:
            self.argos_available = False

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Top: Index control and search
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.update_index_btn = wx.Button(panel, label="Update Index")
        self.update_index_btn.Bind(wx.EVT_BUTTON, self.on_update_index)
        top_sizer.Add(self.update_index_btn, 0, wx.ALL, 5)

        top_sizer.Add(wx.StaticText(panel, label="Search:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.search_ctrl = wx.SearchCtrl(panel, style=wx.TE_PROCESS_ENTER)
        safe_set_descriptive_text(self.search_ctrl, "Filter available Argos packages by language codes or name (e.g. en, es, en_es)")
        top_sizer.Add(self.search_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        self.search_btn = wx.Button(panel, label="Search")
        self.search_btn.Bind(wx.EVT_BUTTON, self.on_search)
        top_sizer.Add(self.search_btn, 0, wx.ALL, 5)

        main_sizer.Add(top_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Middle: Split available packages and installed languages
        split_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Available packages list
        avail_sizer = wx.BoxSizer(wx.VERTICAL)
        avail_sizer.Add(wx.StaticText(panel, label="Available Argos Packages (Index)"), 0, wx.ALL, 5)
        self.available_list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.available_list.InsertColumn(0, "Package Name", width=300)
        self.available_list.InsertColumn(1, "From", width=60)
        self.available_list.InsertColumn(2, "To", width=60)
        self.available_list.InsertColumn(3, "Description", width=300)
        avail_sizer.Add(self.available_list, 1, wx.EXPAND | wx.ALL, 5)

        btns_avail = wx.BoxSizer(wx.HORIZONTAL)
        self.install_pkg_btn = wx.Button(panel, label="Download & Install")
        self.install_pkg_btn.Disable()
        self.install_pkg_btn.Bind(wx.EVT_BUTTON, self.on_install_selected_package)
        btns_avail.Add(self.install_pkg_btn, 0, wx.ALL, 5)

        self.install_file_btn = wx.Button(panel, label="Install from file...")
        self.install_file_btn.Bind(wx.EVT_BUTTON, self.on_install_file)
        btns_avail.Add(self.install_file_btn, 0, wx.ALL, 5)

        avail_sizer.Add(btns_avail, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        split_sizer.Add(avail_sizer, 3, wx.EXPAND | wx.ALL, 5)

        # Installed languages
        inst_sizer = wx.BoxSizer(wx.VERTICAL)
        inst_sizer.Add(wx.StaticText(panel, label="Installed Argos Languages"), 0, wx.ALL, 5)
        self.installed_list = wx.ListBox(panel)
        inst_sizer.Add(self.installed_list, 1, wx.EXPAND | wx.ALL, 5)
        self.refresh_installed_btn = wx.Button(panel, label="Refresh Installed")
        self.refresh_installed_btn.Bind(wx.EVT_BUTTON, self.refresh_installed)
        inst_sizer.Add(self.refresh_installed_btn, 0, wx.ALL | wx.ALIGN_RIGHT, 5)

        split_sizer.Add(inst_sizer, 2, wx.EXPAND | wx.ALL, 5)

        main_sizer.Add(split_sizer, 1, wx.EXPAND | wx.ALL, 5)

        # Status & progress
        status_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.status_text = wx.StaticText(panel, label="")
        status_sizer.Add(self.status_text, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        self.progress = wx.Gauge(panel, range=100, size=(250, 18))
        status_sizer.Add(self.progress, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        main_sizer.Add(status_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Close
        close_btn = wx.Button(panel, wx.ID_CLOSE, label="Close")
        close_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        main_sizer.Add(close_btn, 0, wx.ALIGN_RIGHT | wx.ALL, 8)

        panel.SetSizer(main_sizer)
        panel.Layout()

        # State
        self.available_packages = []  # package objects from argostranslate.package.get_available_packages()
        self._bind_events()
        # Initial population
        self.refresh_installed()
        # If argos not available, notify user
        if not self.argos_available:
            self.available_list.AppendItem(["Argos Translate package not installed. Install `argostranslate` via pip.", "", "", ""])
            self.update_index_btn.Disable()
            self.search_btn.Disable()
            self.install_pkg_btn.Disable()
    def _bind_events(self):
        self.available_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_available_selected)
        self.available_list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_available_deselected)

    def _set_status(self, text, progress=None):
        wx.CallAfter(self.status_text.SetLabel, text)
        if progress is not None:
            wx.CallAfter(self.progress.SetValue, int(progress))

    def on_update_index(self, event):
        if not self.argos_available:
            wx.MessageBox("Argos Translate Python package not installed.", "Error", wx.OK | wx.ICON_ERROR)
            return
        def worker():
            try:
                self._set_status("Updating Argos package index...", 0)
                import argostranslate.package as argos_package
                argos_package.update_package_index()
                self._set_status("Index updated. Refreshing available packages...", 10)
                self._refresh_available_packages()
                self._set_status("Index refreshed.", 100)
            except Exception as e:
                self._set_status(f"Index update failed: {e}", 0)
        threading.Thread(target=worker, daemon=True).start()

    def on_search(self, event):
        term = self.search_ctrl.GetValue().strip().lower()
        self._refresh_available_packages(filter_term=term)

    def _refresh_available_packages(self, filter_term=None):
        if not self.argos_available:
            return
        def worker():
            try:
                self._set_status("Fetching available packages...", 0)
                import argostranslate.package as argos_package
                avail = argos_package.get_available_packages()
                self.available_packages = avail or []
                wx.CallAfter(self.available_list.DeleteAllItems)
                for idx, pkg in enumerate(self.available_packages):
                    from_code = getattr(pkg, "from_code", getattr(pkg, "fromCode", ""))
                    to_code = getattr(pkg, "to_code", getattr(pkg, "toCode", ""))
                    name = getattr(pkg, "name", getattr(pkg, "package_name", str(pkg)))
                    desc = getattr(pkg, "description", "")
                    display = f"{name}"
                    # Apply simple filter matching on codes or name if requested
                    if filter_term:
                        if filter_term not in name.lower() and filter_term not in str(from_code).lower() and filter_term not in str(to_code).lower():
                            continue
                    # Insert into list control on main thread
                    wx.CallAfter(self.available_list.InsertItem, idx, str(display))
                    wx.CallAfter(self.available_list.SetItem, idx, 1, str(from_code))
                    wx.CallAfter(self.available_list.SetItem, idx, 2, str(to_code))
                    wx.CallAfter(self.available_list.SetItem, idx, 3, str(desc)[:300])
                self._set_status(f"Found {len(self.available_packages)} packages.", 100)
            except Exception as e:
                self._set_status(f"Failed to fetch packages: {e}", 0)
        threading.Thread(target=worker, daemon=True).start()

    def on_available_selected(self, event):
        self.install_pkg_btn.Enable()

    def on_available_deselected(self, event):
        self.install_pkg_btn.Disable()

    def on_install_selected_package(self, event):
        sel = self.available_list.GetFirstSelected()
        if sel == -1:
            wx.MessageBox("Please select a package to install.", "Info", wx.OK | wx.ICON_INFORMATION)
            return
        pkg = self.available_packages[sel]
        def worker():
            try:
                self._set_status("Downloading and installing package...", 5)
                
                # This helper now handles download, moving to our local dir, and installing.
                argos_engine.download_and_install_package(pkg)
                
                self._set_status("Installation complete.", 100)
                wx.CallAfter(wx.MessageBox, f"Installed {getattr(pkg,'name',str(pkg))}", "Success", wx.OK | wx.ICON_INFORMATION)
                wx.CallAfter(self.refresh_installed)
            except Exception as e:
                # Use CallAfter for UI updates from the thread
                error_message = f"Failed to install package: {e}"
                wx.CallAfter(self._set_status, error_message, 0)
                wx.CallAfter(wx.MessageBox, error_message, "Error", wx.OK | wx.ICON_ERROR)
        threading.Thread(target=worker, daemon=True).start()

    def refresh_installed(self, event=None):
        self.installed_list.Clear()
        if not self.argos_available:
            self.installed_list.Append("Argos Translate package not installed. Install `argostranslate` via pip.")
            return
        try:
            from argostranslate import translate as argos_translate
            langs = argos_translate.get_installed_languages()
            if not langs:
                self.installed_list.Append("No Argos language packages installed.")
                return
            for lang in langs:
                code = getattr(lang, "code", getattr(lang, "locale_code", str(lang)))
                name = getattr(lang, "name", code)
                self.installed_list.Append(f"{code} - {name}")
        except Exception as e:
            self.installed_list.Append(f"Error listing installed languages: {e}")

    def on_install_file(self, event):
        with wx.FileDialog(self, "Select Argos package (.argosmodel) to install", wildcard="Argos model files (*.argosmodel)|*.argosmodel|All files (*.*)|*.*", style=wx.FD_OPEN) as fd:
            if fd.ShowModal() == wx.ID_CANCEL:
                return
            path = fd.GetPath()
            try:
                import argostranslate.package as argos_package
                argos_package.install_from_path(path)
                wx.MessageBox(f"Installed package from {path}", "Success", wx.OK | wx.ICON_INFORMATION)
            except Exception as e:
                wx.MessageBox(f"Failed to install package: {e}", "Error", wx.OK | wx.ICON_ERROR)
            finally:
                self.refresh_installed()