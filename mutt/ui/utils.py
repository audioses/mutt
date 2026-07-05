
def safe_set_descriptive_text(control, text):
    """Safely set descriptive text on a control, checking if the method exists."""
    if hasattr(control, 'SetDescriptiveText'):
        control.SetDescriptiveText(text)
    elif hasattr(control, 'SetToolTip'):
        control.SetToolTip(text)