import wx
import wx.lib.newevent

# =============================================================================
# THREAD-SAFE CUSTOM EVENTS AND IDs
# =============================================================================
UpdateEvent, EVT_UPDATE = wx.lib.newevent.NewEvent()
ResultEvent, EVT_RESULT = wx.lib.newevent.NewEvent()
ID_PREVIOUS_ENTRY = wx.NewIdRef()
ID_NEXT_ENTRY = wx.NewIdRef()
ID_FOCUS_SOURCE = wx.NewIdRef()
ID_FOCUS_TARGET = wx.NewIdRef()
ID_FOCUS_TOOL = wx.NewIdRef()
ID_SEARCH = wx.NewIdRef()
ID_JUMP = wx.NewIdRef()


# =============================================================================
# CONFIGURATION AND DEFAULTS
# =============================================================================
CONFIG_FILE = "config.json"
PROJECT_FILE_EXT = ".mutt"
DEFAULT_PROMPTS = [
    {"name": "Tool: Generate Variations", "prompt": "Generate {count} translation variations for the source text:\n\n---\n{source_text}\n---\n\nThe current proposed translation is:\n\n---\n{target_text}\n---\n\nThe desired style is '{style}'.{custom_instruction_text}", "system": True},
    {"name": "Tool: Explain Difference", "prompt": "Act as a linguistics expert. Explain the difference in nuance, formality, and potential idiomatic meaning between the source text and the proposed translation. Be concise.\n\nSource: {source_text}\nTranslation: {target_text}", "system": True},
    {"name": "Tool: Check for Errors", "prompt": "Act as a proofreader. Review the translation for grammatical errors, typos, or awkward phrasing compared to the source text. If no errors are found, respond with 'No errors found.'. If errors are found, provide a corrected version and a brief, one-sentence explanation of the change.\n\nSource: {source_text}\nTranslation: {target_text}", "system": True},
    {"name": "Tool: Cultural Context", "prompt": "Act as a localization consultant. Analyze the translation for any unintended cultural implications, sensitivities, or references that might not be appropriate for a general audience in the target language. If there are no issues, respond with 'Culturally appropriate.'.\n\nSource: {source_text}\nTranslation: {target_text}", "system": True},
    {"name": "Tool: Free Chat", "prompt": "You are a helpful translation assistant. The user has the following context:\n\nSource Text: {source_text}\nProposed Translation: {target_text}\n\nNow, please answer the user's question: {user_input}", "system": True},
    {"name": "Tool: Get Etymology", "prompt": "Provide a concise etymology for the following word: {source_text}", "system": True}
]
