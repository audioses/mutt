import wx
import os
# Optional Hugging Face engine
try:
    from mutt.engines import hf_engine
except Exception:
    hf_engine = None

from ai_translator import AITranslator
from mutt.ui.dialogs.local_models import LocalModelDialog
from mutt.ui.dialogs.hf import HuggingFacePanel
from mutt.ui.dialogs.argos import ArgosModelDialog

class APISetupDialog(wx.Dialog):
    def __init__(self, parent, config, api_helpers):
        super().__init__(parent, title="API Setup", size=(600, 700))
        self.config = config
        self.APIHelper = api_helpers
        self.notebook = wx.Notebook(self)
        self.api_choices = ["OpenAI GPT", "Google Gemini", "OpenRouter", "Custom (OpenAI-Compatible)", "Local Models", "HuggingFace", "Argos Translate"]

        self.basic_tab = wx.Panel(self.notebook)
        self.advanced_tab = wx.Panel(self.notebook)
        self.notebook.AddPage(self.basic_tab, "Basic Settings")
        self.notebook.AddPage(self.advanced_tab, "Advanced Settings")

        self.setup_basic_tab()
        self.setup_advanced_tab()

        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(self, wx.ID_OK)
        cancel_btn = wx.Button(self, wx.ID_CANCEL)
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.notebook, 1, wx.ALL | wx.EXPAND, 10)
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.CENTER, 10)
        self.SetSizer(main_sizer)

        self.Bind(wx.EVT_BUTTON, self.on_ok, ok_btn)

        last_provider = self.config.get("last_provider", self.api_choices[0])
        if last_provider in self.api_choices:
            self.provider_radio.SetSelection(self.api_choices.index(last_provider))
        self.load_provider_settings()

    def setup_basic_tab(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        # Single column: in a multi-column RadioBox Up/Down only walks one
        # column, so providers in the second column (Gemini, Custom,
        # HuggingFace) were unreachable with the arrow keys alone.
        self.provider_radio = wx.RadioBox(self.basic_tab, label="API Provider", choices=self.api_choices, majorDimension=1, style=wx.RA_SPECIFY_COLS)
        sizer.Add(self.provider_radio, 0, wx.ALL | wx.EXPAND, 5)

        sizer.Add(wx.StaticText(self.basic_tab, label="API Key:"), 0, wx.ALL, 5)
        self.api_key_text = wx.TextCtrl(self.basic_tab, style=wx.TE_PASSWORD)
        sizer.Add(self.api_key_text, 0, wx.ALL | wx.EXPAND, 5)

        # Base URL — only shown for "Custom (OpenAI-Compatible)"
        self.base_url_label = wx.StaticText(self.basic_tab, label="Base URL (OpenAI-compatible endpoint):")
        self.base_url_text = wx.TextCtrl(self.basic_tab)
        self.base_url_text.SetHint("e.g. https://api.groq.com/openai/v1 or http://localhost:8080/v1")
        sizer.Add(self.base_url_label, 0, wx.ALL, 5)
        sizer.Add(self.base_url_text, 0, wx.ALL | wx.EXPAND, 5)

        sizer.Add(wx.StaticText(self.basic_tab, label="Model:"), 0, wx.ALL, 5)
        self.model_combo = wx.ComboBox(self.basic_tab, style=wx.CB_DROPDOWN)
        sizer.Add(self.model_combo, 0, wx.ALL | wx.EXPAND, 5)

        self.fetch_models_btn = wx.Button(self.basic_tab, label="Fetch Available Models")
        sizer.Add(self.fetch_models_btn, 0, wx.ALL, 5)
        self.manage_local_btn = wx.Button(self.basic_tab, label="Manage Local Models")
        sizer.Add(self.manage_local_btn, 0, wx.ALL, 5)
        self.manage_hf_btn = wx.Button(self.basic_tab, label="Manage Hugging Face Models")
        sizer.Add(self.manage_hf_btn, 0, wx.ALL, 5)

        sizer.Add(wx.StaticText(self.basic_tab, label="Local Backend:"), 0, wx.ALL, 5)
        self.local_backend_radio = wx.RadioBox(self.basic_tab, label="", choices=["Llama.cpp", "LM Studio"], majorDimension=2, style=wx.RA_SPECIFY_COLS)
        sizer.Add(self.local_backend_radio, 0, wx.ALL | wx.EXPAND, 5)

        sizer.Add(wx.StaticText(self.basic_tab, label=f"Batch Size (1-{AITranslator.MAX_BATCH_SIZE}):"), 0, wx.ALL, 5)
        self.batch_size_spin = wx.SpinCtrl(
            self.basic_tab, min=1, max=AITranslator.MAX_BATCH_SIZE,
            initial=min(int(self.config.get("batch_size", 50)), AITranslator.MAX_BATCH_SIZE),
        )
        sizer.Add(self.batch_size_spin, 0, wx.ALL | wx.EXPAND, 5)
     
        # Argos-specific settings (hidden unless provider == Argos Translate)
        self.argos_strategy_label = wx.StaticText(self.basic_tab, label="Argos Fallback Strategy:")
        self.argos_strategy_choice = wx.ComboBox(self.basic_tab, choices=["pivot", "prompt_install", "auto_install"], style=wx.CB_READONLY)
        self.argos_strategy_choice.SetValue("pivot")
        sizer.Add(self.argos_strategy_label, 0, wx.ALL, 5)
        sizer.Add(self.argos_strategy_choice, 0, wx.ALL | wx.EXPAND, 5)
     
        self.argos_pivots_label = wx.StaticText(self.basic_tab, label="Argos Pivot Order (comma-separated):")
        self.argos_pivots_text = wx.TextCtrl(self.basic_tab, value="en")
        sizer.Add(self.argos_pivots_label, 0, wx.ALL, 5)
        sizer.Add(self.argos_pivots_text, 0, wx.ALL | wx.EXPAND, 5)
     
        # Hide Argos controls by default
        try:
            self.argos_strategy_label.Hide()
            self.argos_strategy_choice.Hide()
            self.argos_pivots_label.Hide()
            self.argos_pivots_text.Hide()
        except Exception:
            pass
     
        self.basic_tab.SetSizer(sizer)
     
        self.provider_radio.Bind(wx.EVT_RADIOBOX, self.on_provider_change)
        self.fetch_models_btn.Bind(wx.EVT_BUTTON, self.on_fetch_models)
        self.manage_local_btn.Bind(wx.EVT_BUTTON, self.on_manage_local_models)
        # Manage Hugging Face models button (may be disabled if dependencies missing)
        try:
            self.manage_hf_btn.Bind(wx.EVT_BUTTON, self.on_manage_hf_models)
        except Exception:
            pass

    def setup_advanced_tab(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self.advanced_tab, label="Temperature (Creativity):"), 0, wx.ALL, 5)
        self.temperature_text = wx.TextCtrl(self.advanced_tab, value=str(self.config.get("temperature", 0.1)))
        sizer.Add(self.temperature_text, 0, wx.ALL | wx.EXPAND, 5)

        sizer.Add(wx.StaticText(self.advanced_tab, label="Max Tokens per Response:"), 0, wx.ALL, 5)
        self.max_tokens_spin = wx.SpinCtrl(self.advanced_tab, min=1, max=999999, initial=self.config.get("max_tokens", 4000))
        sizer.Add(self.max_tokens_spin, 0, wx.ALL | wx.EXPAND, 5)

        sizer.Add(wx.StaticText(self.advanced_tab, label="Max Tokens per Batch:"), 0, wx.ALL, 5)
        self.max_batch_tokens_spin = wx.SpinCtrl(self.advanced_tab, min=1, max=400000, initial=self.config.get("max_batch_tokens", 16000))
        sizer.Add(self.max_batch_tokens_spin, 0, wx.ALL | wx.EXPAND, 5)
        
        # NEW: Contextual AI Prompts settings
        self.enable_context_checkbox = wx.CheckBox(self.advanced_tab, label="Enable Surrounding Context")
        self.enable_context_checkbox.SetValue(self.config.get("enable_surrounding_context", True))
        sizer.Add(self.enable_context_checkbox, 0, wx.ALL, 5)

        sizer.Add(wx.StaticText(self.advanced_tab, label="Previous Context Size (entries):"), 0, wx.ALL, 5)
        self.context_previous_spin = wx.SpinCtrl(self.advanced_tab, min=0, max=10, initial=self.config.get("context_previous_size", 2))
        sizer.Add(self.context_previous_spin, 0, wx.ALL | wx.EXPAND, 5)

        sizer.Add(wx.StaticText(self.advanced_tab, label="Next Context Size (entries):"), 0, wx.ALL, 5)
        self.context_next_spin = wx.SpinCtrl(self.advanced_tab, min=0, max=10, initial=self.config.get("context_next_size", 2))
        sizer.Add(self.context_next_spin, 0, wx.ALL | wx.EXPAND, 5)

        self.advanced_tab.SetSizer(sizer)
        self.enable_context_checkbox.Bind(wx.EVT_CHECKBOX, self.on_enable_context_changed)
        self.on_enable_context_changed(None) # Set initial state

    def on_enable_context_changed(self, event):
        enabled = self.enable_context_checkbox.GetValue()
        self.context_previous_spin.Enable(enabled)
        self.context_next_spin.Enable(enabled)

    def load_provider_settings(self):
        provider = self.api_choices[self.provider_radio.GetSelection()]
        is_custom = provider == "Custom (OpenAI-Compatible)"
        self.local_backend_radio.Show(provider == "Local Models")
        self.manage_local_btn.Show(provider == "Local Models")
        self.base_url_label.Show(is_custom)
        self.base_url_text.Show(is_custom)
        self.Layout()

        provider_settings = self.config.get("providers", {}).get(provider, {})
        self.api_key_text.SetValue(provider_settings.get("api_key", ""))
        self.base_url_text.SetValue(provider_settings.get("base_url", "") if is_custom else "")
        current_model = provider_settings.get("api_model", "")
        self.local_backend_radio.SetSelection(0 if self.config.get("local_backend", "Llama.cpp") == "Llama.cpp" else 1)
 
        # Argos: models/packages managed via package manager; display helpful placeholder
        if provider == "Argos Translate":
            self.model_combo.SetItems(["Argos packages managed via 'Manage Argos Packages'"])
            self.model_combo.SetValue("Argos packages managed via 'Manage Argos Packages'")
        elif provider == "HuggingFace":
            # Hugging Face models are managed via the Manage Hugging Face Models dialog
            hf_model = provider_settings.get("api_model", "")
            if hf_model:
                self.model_combo.SetItems([hf_model, "Manage Models..."])
                self.model_combo.SetValue(hf_model)
            else:
                self.model_combo.SetItems(["Manage Hugging Face Models..."])
                self.model_combo.SetSelection(0)
        else:
            if current_model:
                self.model_combo.SetItems([current_model, "Fetch new list..."])
                self.model_combo.SetValue(current_model)
            else:
                self.model_combo.SetItems(["Enter API Key and Fetch"])
                self.model_combo.SetSelection(0)
 
        # Show/hide Argos controls
        try:
            if provider == "Argos Translate":
                self.argos_strategy_label.Show()
                self.argos_strategy_choice.Show()
                self.argos_pivots_label.Show()
                self.argos_pivots_text.Show()
                # Load saved strategy/pivots if present
                argos_strategy = provider_settings.get("argos_strategy", "pivot")
                argos_pivots = provider_settings.get("argos_pivots", ["en"])
                self.argos_strategy_choice.SetValue(argos_strategy)
                self.argos_pivots_text.SetValue(",".join(argos_pivots) if isinstance(argos_pivots, list) else str(argos_pivots))
            else:
                self.argos_strategy_label.Hide()
                self.argos_strategy_choice.Hide()
                self.argos_pivots_label.Hide()
                self.argos_pivots_text.Hide()
        except Exception:
            # If controls are not present for some reason, ignore
            pass
 
        self.on_enable_context_changed(None) # Ensure context spins are correctly enabled/disabled

    def on_provider_change(self, event):
        self.load_provider_settings()

    def on_fetch_models(self, event):
        api_key = self.api_key_text.GetValue()
        provider = self.api_choices[self.provider_radio.GetSelection()]
        # Hugging Face local transformers usage does not require an API key
        if not api_key and provider not in ["OpenRouter", "Local Models", "HuggingFace"]:
            wx.MessageBox("API Key required.", "Warning")
            return

        self.model_combo.SetItems(["Fetching..."])
        wx.CallAfter(wx.BeginBusyCursor)
        try:
            if provider == "HuggingFace":
                # For Hugging Face, return locally cached models (managed via HuggingFacePanel)
                if hf_engine and getattr(hf_engine, "HF_AVAILABLE", False):
                    try:
                        mgr = hf_engine.HFModelManager()
                        models = mgr.list_cached_models()
                    except Exception:
                        models = []
                else:
                    models = []
            elif provider == "Custom (OpenAI-Compatible)":
                base_url = self.base_url_text.GetValue().strip()
                if not base_url:
                    wx.MessageBox(
                        "Base URL is required for Custom (OpenAI-Compatible).\n"
                        "Example: https://api.groq.com/openai/v1",
                        "Warning",
                    )
                    self.model_combo.SetItems(["Enter Base URL and Fetch"])
                    self.model_combo.SetSelection(0)
                    return
                models = self.APIHelper.get_custom_openai_models(api_key, base_url)
            else:
                models = {
                    "OpenAI GPT": self.APIHelper.get_openai_models,
                    "Google Gemini": self.APIHelper.get_google_models,
                    "OpenRouter": self.APIHelper.get_openrouter_models,
                    "Local Models": self.APIHelper.get_local_models
                }[provider](api_key)
        finally:
            wx.CallAfter(wx.EndBusyCursor)

        if not models:
            self.model_combo.SetItems(["No models found."])
        else:
            self.model_combo.SetItems(models)
        self.model_combo.SetSelection(0)

    def on_manage_local_models(self, event):
        with LocalModelDialog(self) as dlg:
            dlg.ShowModal()
        if self.api_choices[self.provider_radio.GetSelection()] == "Local Models":
            self.on_fetch_models(None)

    def on_manage_hf_models(self, event):
        # Open the Hugging Face manager panel (lightweight, depends on hf_engine availability)
        with HuggingFacePanel(self) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                selected = getattr(dlg, "selected_model_id", None)
                device = getattr(dlg, "selected_device", None)
                if selected:
                    # Update the model combo and persist choice to config
                    self.model_combo.SetItems([selected, "Fetch new list..."])
                    self.model_combo.SetValue(selected)
                    self.config.setdefault("providers", {})["HuggingFace"] = {"api_key": "", "api_model": selected, "device": device}
                    # If HuggingFace is the currently selected provider, ensure UI reflects the model
                    if self.api_choices[self.provider_radio.GetSelection()] == "HuggingFace":
                        self.model_combo.SetValue(selected)

    def on_manage_argos_models(self, event):
        with ArgosModelDialog(self) as dlg:
            dlg.ShowModal()
        if self.api_choices[self.provider_radio.GetSelection()] == "Argos Translate":
            self.load_provider_settings()

    def on_ok(self, event):
        provider = self.api_choices[self.provider_radio.GetSelection()]
        api_key = self.api_key_text.GetValue().strip()
        model = self.model_combo.GetValue().strip()

        # Allow Hugging Face / Local / Custom to operate without an API key
        if not api_key and provider not in ["Local Models", "HuggingFace", "Custom (OpenAI-Compatible)"]:
            wx.MessageBox("API Key is required.", "Error")
            return
        if not model:
            wx.MessageBox("Model is required.", "Error")
            return

        if provider == "Custom (OpenAI-Compatible)":
            base_url = self.base_url_text.GetValue().strip()
            if not base_url:
                wx.MessageBox("Base URL is required for Custom (OpenAI-Compatible).", "Error")
                return
            self.config.setdefault("providers", {})[provider] = {
                "api_key": api_key,
                "api_model": model,
                "base_url": base_url,
            }
        elif provider == "HuggingFace":
            # For Hugging Face, we also need to store the device preference, which is managed in the HuggingFacePanel
            # The panel already saves the config, so we just need to ensure the main dialog doesn't overwrite it.
            if "HuggingFace" not in self.config.get("providers", {}):
                 self.config.setdefault("providers", {})[provider] = {"api_key": "", "api_model": model, "device": "cpu", "hf_cache_dir": os.path.join("models", "hf_cache")}
        else:
            self.config.setdefault("providers", {})[provider] = {"api_key": api_key, "api_model": model}
        self.config["last_provider"] = provider
        self.config["batch_size"] = self.batch_size_spin.GetValue()
        self.config["local_backend"] = self.local_backend_radio.GetStringSelection()

        try:
            self.config["temperature"] = float(self.temperature_text.GetValue())
            self.config["max_tokens"] = self.max_tokens_spin.GetValue()
            self.config["max_batch_tokens"] = self.max_batch_tokens_spin.GetValue()
            self.config["enable_surrounding_context"] = self.enable_context_checkbox.GetValue()
            self.config["context_previous_size"] = self.context_previous_spin.GetValue()
            self.config["context_next_size"] = self.context_next_spin.GetValue()
        except ValueError:
            wx.MessageBox("Invalid advanced setting.", "Error")
            return
        self.EndModal(wx.ID_OK)