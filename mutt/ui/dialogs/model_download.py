import wx
from typing import Optional
from local_model_manager import LocalModelManager

class ModelDownloadDialog(wx.Dialog):
    # ... (This class is unchanged)
    def __init__(self, parent, model_id, model_name, preferred_quant: Optional[str] = "Auto"):
        super(ModelDownloadDialog, self).__init__(parent, title=f"Downloading {model_name}", size=(450, 150))
        self.model_id = model_id; self.model_name = model_name; self.model_manager = LocalModelManager(); self.download_success = None
        self.preferred_quant = preferred_quant or "Auto"
        panel = wx.Panel(self); vbox = wx.BoxSizer(wx.VERTICAL)
        self.status_text = wx.StaticText(panel, label=f"Preparing to download {model_name} (Preferred: {self.preferred_quant})...")
        vbox.Add(self.status_text, 0, wx.ALL | wx.EXPAND, 15)
        self.progress = wx.Gauge(panel, range=100, size=(400, 25), style=wx.GA_HORIZONTAL)
        vbox.Add(self.progress, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 15)
        panel.SetSizer(vbox); self.Layout()
    def update_progress(self, value, status):
        wx.CallAfter(self.progress.SetValue, int(value)); wx.CallAfter(self.status_text.SetLabel, status)
        if value >= 100: wx.CallAfter(self.EndModal, wx.ID_OK)
    def start_download(self):
        # Pass preferred_quant through to the downloader so it can try to select matching GGUF
        self.model_manager.download_model(self.model_id, self.model_name, self.update_progress, preferred_quant=self.preferred_quant)