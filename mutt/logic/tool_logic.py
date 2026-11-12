import wx
from ai_translator import AITranslator
from mutt.constants import ResultEvent
import yaml
from pathlib import Path
from mutt.ui.dynamic_panel import get_data_from_controls

def run_tool_thread(parent_frame):
    try:
        selected_tool_name = parent_frame.chat_mode_radio.GetStringSelection()
        
        # Check if this is a YAML-based mode
        yaml_mode_data = None
        yaml_modes_dir = Path("modes")
        if yaml_modes_dir.exists():
            for yaml_file in yaml_modes_dir.glob("*.mode.yaml"):
                try:
                    with open(yaml_file, 'r', encoding='utf-8') as f:
                        mode_data = yaml.safe_load(f)
                        mode_name = mode_data.get("name", yaml_file.stem)
                        if mode_name == selected_tool_name:
                            yaml_mode_data = mode_data
                            break
                except Exception:
                    pass
        
        # Initialize translator
        active_provider = parent_frame.config.get("last_provider")
        settings = parent_frame.config.get("providers", {}).get(active_provider, {})
        translator = AITranslator(active_provider, settings.get("api_key"), settings.get("api_model"), temperature=parent_frame.config.get("temperature", 0.7), extra_settings=settings)
        
        if yaml_mode_data:
            # Handle YAML-based mode
            prompt_template = yaml_mode_data.get("prompt", "")
            entry = parent_frame.translated_po_entries[parent_frame.current_entry_index]
            
            # Get values from UI controls
            user_input = ""
            if hasattr(parent_frame, 'tool_input') and not isinstance(parent_frame.tool_input, wx.Button):
                user_input = parent_frame.tool_input.GetValue().strip()
            
            # Replace standard placeholders in prompt
            prompt_text = prompt_template.replace("{{source_text}}", entry["msgid"])
            prompt_text = prompt_text.replace("{{target_text}}", entry["msgstr"])
            prompt_text = prompt_text.replace("{{user_input}}", user_input)
            
            # Replace any other dynamic placeholders from UI elements
            if hasattr(parent_frame, 'dynamic_tool_data_store'):
                dynamic_data = get_data_from_controls(parent_frame.dynamic_tool_data_store)
                for key, value in dynamic_data.items():
                    prompt_text = prompt_text.replace("{{" + key + "}}", str(value))
            
            result_text, _ = translator._execute_single_prompt(prompt_text)
            
        else:
            # Handle pre-coded Python modes (built-in tools)
            # Check if this is a mode-specific execution
            if (hasattr(parent_frame, 'instantiated_modes') and
                selected_tool_name in parent_frame.instantiated_modes):
                # Execute the mode-specific logic
                mode_instance = parent_frame.instantiated_modes[selected_tool_name]
                
                # Prepare data for the mode
                entry = parent_frame.translated_po_entries[parent_frame.current_entry_index]
                data = {
                    "source_text": entry["msgid"],
                    "target_text": entry["msgstr"],
                    "selected_text": entry["msgid"]  # Default to source text
                }
                
                # Add any mode-specific UI data
                if hasattr(parent_frame, 'mode_specific_panel'):
                    # For modes that have their own UI, we would extract data from their controls here
                    # This would depend on how each mode implements its UI
                    pass
                
                # Execute the mode
                try:
                    result_text = mode_instance.execute(data)
                except Exception as e:
                    raise RuntimeError(f"Error executing mode {selected_tool_name}: {e}")
            else:
                # Handle legacy prompt-based tools
                selected_tool_name = "Tool: " + selected_tool_name
                prompt_obj = next((p for p in parent_frame.config["prompts"] if p["name"] == selected_tool_name), None)
                if not prompt_obj: raise ValueError("Selected tool prompt not found.")
                entry = parent_frame.translated_po_entries[parent_frame.current_entry_index]
                
                # Safely get values from UI controls, checking their types first
                custom_instruction = ""
                if hasattr(parent_frame, 'variation_custom_prompt') and not isinstance(parent_frame.variation_custom_prompt, wx.Button):
                    custom_instruction = parent_frame.variation_custom_prompt.GetValue().strip()
                custom_instruction_text = f"\nAdditionally, follow this instruction: {custom_instruction}" if custom_instruction else ""
                
                # Get values from other controls with type checking
                count_value = 3  # Default value
                style_value = "Default"  # Default value
                user_input = ""  # Default value
                
                if hasattr(parent_frame, 'variation_count') and not isinstance(parent_frame.variation_count, wx.Button):
                    count_value = parent_frame.variation_count.GetValue()
                    
                if hasattr(parent_frame, 'variation_style') and not isinstance(parent_frame.variation_style, wx.Button):
                    style_value = parent_frame.variation_style.GetValue()
                    
                if hasattr(parent_frame, 'tool_input') and not isinstance(parent_frame.tool_input, wx.Button):
                    user_input = parent_frame.tool_input.GetValue().strip()
                
                prompt_text = prompt_obj["prompt"].format(
                    source_text=entry["msgid"],
                    target_text=entry["msgstr"],
                    count=count_value,
                    style=style_value,
                    custom_instruction_text=custom_instruction_text,
                    user_input=user_input
                )
                result_text, _ = translator._execute_single_prompt(prompt_text)
        
        result_data = [line.strip() for line in result_text.split('\n') if line.strip()] if "Variations" in selected_tool_name else result_text
        wx.PostEvent(parent_frame, ResultEvent(source='tool', result=result_data, error=None))
    except Exception as e:
        wx.PostEvent(parent_frame, ResultEvent(source='tool', error=e))