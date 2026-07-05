# Pluggable Modes Architecture for Translator's Toolbox

## 1. Overview

This document outlines a **hybrid technical architecture** for a modular, pluggable system for the "Translator's Toolbox" in MUTT. The goal is to replace the current hardcoded implementation with a dynamic system that supports both powerful, developer-created modes and safe, user-created modes.

This hybrid approach will enable easier maintenance, a rich feature set, and a future "marketplace" where users can create and share their own tools without needing to code.

## 2. Core Principles

*   **Hybrid System:** The architecture supports two types of modes:
    *   **Internal Modes (.py):** For complex, powerful features built directly into the application.
    *   **External Modes (.mode.yaml):** For safe, declarative, user-created modes that are easy to build and share.
*   **Discoverability:** The application will automatically detect and load all valid modes from both internal and external directories at runtime.
*   **Declarative UI:** All modes, regardless of type, will define their user interface using a simple, data-driven structure.
*   **Sandboxing:** User-created modes are sandboxed and can only perform safe, predefined actions (like running a prompt), preventing security risks.

## 3. Directory Structure

### Internal (Python-based) Modes

Core modes built by developers will reside in a new dedicated package:
```
mutt/
└── modes/
    ├── __init__.py
    ├── base_mode.py              # Defines the abstract base class for internal modes
    ├── generate_variations.py    # Example: Internal "Generate Variations" mode
    └── free_chat.py              # Example: Internal "Free Chat" mode
```

### External (User-Created) Modes

User-created modes will be loaded from a user-accessible directory. This allows users to add or modify modes without altering the application's core files. The location will be OS-dependent (e.g., `~/.config/mutt/modes` on Linux, `%APPDATA%/MUTT/modes` on Windows).

```
<UserData>/
└── mutt/
    └── modes/
        ├── simple_proofreader.mode.yaml
        └── formal_tone_converter.mode.yaml
```

## 4. Mode Definition: A Hybrid Approach

### Internal Mode Definition: The `BaseMode` Interface

For internal modes, a new abstract base class, `BaseMode`, will be created in `mutt/modes/base_mode.py`. All internal mode modules must contain a class that inherits from this base class.

### `base_mode.py` (Pseudo-code for Internal Modes)

```python
from abc import ABC, abstractmethod

class BaseMode(ABC):
    """
    Abstract base class for all Translator's Toolbox modes.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The display name of the mode."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """A brief description of what the mode does."""
        pass

    @abstractmethod
    def get_ui_layout(self) -> list[dict]:
        """
        Returns a list of dictionaries defining the UI widgets for this mode.
        """
        pass

    @abstractmethod
    def execute(self, context: dict) -> dict:
        """
        Executes the mode's logic.

        Args:
            context (dict): A dictionary containing input data from the main UI,
                            such as 'source_text', 'target_text', and values
                            from the mode's own UI controls.

        Returns:
            dict: A dictionary containing the results to be displayed,
                  e.g., {'output_text': 'Result', 'update_list': [...]}.
        """
        pass
```

### External Mode Definition: The `.mode.yaml` Format

User-created modes are defined in simple YAML files. These files are purely declarative and do not contain any executable code. They are essentially powerful prompt templates with a custom UI.

#### `simple_proofreader.mode.yaml` (Example)
```yaml
# The display name of the mode
name: "Simple Proofreader"

# A short description of what it does
description: "Checks the target text for grammatical errors and suggests a fix."

# Defines the user interface for the mode
ui:
  - type: TextArea
    id: "suggestion_output"
    label: "Suggested Correction:"
    options:
      read_only: true
  - type: Button
    id: "run_proofread"
    label: "Proofread Text"

# Defines the sandboxed logic to be executed
logic:
  # This mode uses a prompt template sent to the AI
  type: "prompt_template"
  
  # The prompt to be sent to the AI. Variables are injected from the UI context.
  template: |
    Please proofread the following text and provide a corrected version.
    Do not add any commentary, just provide the corrected text.

    Text to proofread:
    "{{target_text}}"
  
  # The ID of the UI widget where the AI's response should be placed.
  output_to: "suggestion_output"
```

## 5. Declarative UI Configuration

The UI for both internal and external modes is defined declaratively.
*   **Internal Modes:** Via the `get_ui_layout()` method.
*   **External Modes:** Via the `ui` key in the `.mode.yaml` file.

The main application will parse this data and dynamically generate the `wx.Panel` for the mode.

### Supported Widget Types:

| `type` | Description | `id` | `label` | `options` | Example |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `TextInput` | A single-line text input field. | Required | Required | - | `{'type': 'TextInput', 'id': 'api_key', 'label': 'API Key'}` |
| `NumericInput` | An input for numbers (`wx.SpinCtrl`). | Required | Required | `{'min': 0, 'max': 10, 'initial': 3}` | `{'type': 'NumericInput', 'id': 'num_variations', 'label': 'Variations'}` |
| `ComboBox` | A dropdown list. | Required | Required | `{'choices': ['A', 'B']}` | `{'type': 'ComboBox', 'id': 'style', 'label': 'Style'}` |
| `TextArea` | A multi-line text area. | Required | Required | `{'read_only': True}` | `{'type': 'TextArea', 'id': 'chat_history', 'label': 'History'}` |
| `InteractiveList` | A `wx.ListBox` for displaying and interacting with results. | Required | Required | - | `{'type': 'InteractiveList', 'id': 'variations_list', 'label': 'Results'}` |
| `Button` | A standard `wx.Button`. | Required | Required | - | `{'type': 'Button', 'id': 'submit_btn', 'label': 'Generate'}` |

The `id` of each widget will be used as the key in the `context` dictionary passed to the `execute` method.

## 6. Discovery and Loading Mechanism

The discovery mechanism will be extended to find both types of modes.

### `main.py` (Pseudo-code for hybrid discovery)

```python
import pkgutil
import importlib
import os
import yaml
from mutt.modes.base_mode import BaseMode

def discover_modes():
    """Discovers and instantiates all valid internal and external modes."""
    loaded_modes = {}
    
    # 1. Discover internal Python-based modes
    internal_package = importlib.import_module('mutt.modes')
    for _, name, _ in pkgutil.iter_modules(internal_package.__path__):
        if name == 'base_mode':
            continue
        try:
            module = importlib.import_module(f'mutt.modes.{name}')
            for attribute in dir(module):
                cls = getattr(module, attribute)
                if isinstance(cls, type) and issubclass(cls, BaseMode) and cls is not BaseMode:
                    instance = cls()
                    loaded_modes[instance.name] = instance
        except Exception as e:
            print(f"Error loading internal mode '{name}': {e}")

    # 2. Discover external YAML-based modes
    user_modes_path = get_user_modes_directory() # Helper to get platform-specific path
    if os.path.exists(user_modes_path):
        for filename in os.listdir(user_modes_path):
            if filename.endswith('.mode.yaml'):
                try:
                    with open(os.path.join(user_modes_path, filename), 'r') as f:
                        yaml_data = yaml.safe_load(f)
                        # The YAML data is wrapped in a generic runner class
                        # that conforms to the BaseMode interface.
                        instance = YAMLModeRunner(yaml_data)
                        loaded_modes[instance.name] = instance
                except Exception as e:
                    print(f"Error loading external mode '{filename}': {e}")
                        
    return loaded_modes

# A generic runner class that makes YAML modes compatible with the system
class YAMLModeRunner:
    def __init__(self, config):
        self._config = config
        self.name = config['name']
        self.description = config['description']

    def get_ui_layout(self):
        return self._config['ui']

    def execute(self, context):
        # This generic execute method handles all YAML-based modes.
        logic = self._config['logic']
        if logic['type'] == 'prompt_template':
            # 1. Render the prompt template with variables from the context
            prompt = logic['template'].format(**context)
            
            # 2. Call the main app's AI translator
            # (Requires passing a reference to the AITranslator or a callback)
            ai_response = context['ai_translator'].translate_text(prompt)
            
            # 3. Return the result to be placed in the specified output widget
            output_widget_id = logic['output_to']
            return {output_widget_id: ai_response}
        return {}

```

## 7. Data Flow and Execution Life Cycle

1.  **Discovery:** All internal and external modes are discovered at application startup. YAML modes are wrapped in a `YAMLModeRunner` instance.
2.  **Selection:** The user selects a mode from a unified dropdown list.
3.  **UI Generation:** The main application calls the selected mode's `get_ui_layout()` method (whether it's an internal mode or a `YAMLModeRunner`) and dynamically builds the UI panel.
4.  **User Interaction:** The user interacts with the generated UI.
5.  **Execution:** When the user triggers the primary action:
    a. The main application gathers the UI state into a `context` dictionary. **Crucially, a reference to the application's AI Translator instance is also included.**
    b. The `execute()` method of the mode instance is called.
6.  **Logic Processing:**
    *   For an **Internal Mode**, its custom Python code runs.
    *   For an **External Mode**, the `YAMLModeRunner.execute()` method runs, renders the prompt, calls the AI translator via the context, and prepares the result.
7.  **Return Results:** The `execute()` method returns a dictionary of results. The keys in this dictionary correspond to the `id` of the UI widgets to be updated.
8.  **UI Update:** The main application receives the result dictionary and updates the corresponding UI elements (e.g., populates a `TextArea` or `InteractiveList`).

## 8. Example Mode Implementations

### Internal Mode: `generate_variations.py`

```python
from .base_mode import BaseMode
# from some_ai_client import get_ai_variations

class GenerateVariationsMode(BaseMode):
    @property
    def name(self) -> str:
        return "Generate Variations"

    @property
    def description(self) -> str:
        return "Generates multiple translation variations for the source text."

    def get_ui_layout(self) -> list[dict]:
        return [
            {'type': 'NumericInput', 'id': 'num_variations', 'label': 'Number of Variations:', 'options': {'min': 1, 'max': 10, 'initial': 3}},
            {'type': 'Button', 'id': 'generate_btn', 'label': 'Generate'},
            {'type': 'InteractiveList', 'id': 'variations_list', 'label': 'Generated Variations:'}
        ]

    def execute(self, context: dict) -> dict:
        source_text = context.get('source_text', '')
        num_variations = context.get('num_variations', 3)

        # variations = get_ai_variations(source_text, count=num_variations)
        # Mock implementation:
        variations = [f"{source_text} (variation {i+1})" for i in range(num_variations)]

        return {'variations_list': variations}
```

### Internal Mode: `free_chat.py`

```python
from .base_mode import BaseMode
# from some_ai_client import chat_with_ai

class FreeChatMode(BaseMode):
    @property
    def name(self) -> str:
        return "Free Chat"

    @property
    def description(self) -> str:
        return "Have a free-form chat with the AI about the translation."

    def get_ui_layout(self) -> list[dict]:
        return [
            {'type': 'TextArea', 'id': 'chat_history', 'label': 'Chat History:', 'options': {'read_only': True}},
            {'type': 'TextInput', 'id': 'user_prompt', 'label': 'Your Message:'},
            {'type': 'Button', 'id': 'send_btn', 'label': 'Send'},
        ]

    def execute(self, context: dict) -> dict:
        user_prompt = context.get('user_prompt', '')
        history = context.get('chat_history', '')
        source_text = context.get('source_text', '')
        
        # full_prompt = f"Context: '{source_text}'\n\nUser: {user_prompt}"
        # ai_response = chat_with_ai(full_prompt)
        # Mock implementation:
        ai_response = f"AI response to '{user_prompt}'"

        new_history = f"{history}\n> User: {user_prompt}\n> AI: {ai_response}\n"
        
        return {'chat_history': new_history, 'user_prompt': ''} # Clear prompt after sending
```

## 9. Mermaid Diagram: Hybrid Data Flow

```mermaid
sequenceDiagram
    participant User
    participant MainApp
    participant AITranslator
    participant InternalMode as Internal Mode (.py)
    participant ExternalMode as External Mode (.yaml)

    alt Application Startup
        MainApp->>MainApp: discover_modes()
        MainApp->>InternalMode: Discover and instantiate
        MainApp->>ExternalMode: Discover, parse, and wrap in YAMLModeRunner
    end

    User->>MainApp: Selects a mode
    
    alt Internal Mode Execution
        MainApp->>InternalMode: get_ui_layout()
        InternalMode-->>MainApp: Returns UI definition
        MainApp->>MainApp: Renders UI
        User->>MainApp: Clicks "Generate" button
        MainApp->>InternalMode: execute(context)
        InternalMode->>InternalMode: Runs custom Python logic
        InternalMode-->>MainApp: Returns result dict
    end

    alt External Mode Execution
        MainApp->>ExternalMode: get_ui_layout()
        ExternalMode-->>MainApp: Returns UI definition from YAML
        MainApp->>MainApp: Renders UI
        User->>MainApp: Clicks "Run" button
        MainApp->>ExternalMode: execute(context with ai_translator)
        ExternalMode->>ExternalMode: Renders prompt template from YAML
        ExternalMode->>AITranslator: translate_text(rendered_prompt)
        AITranslator-->>ExternalMode: Returns AI response
        ExternalMode-->>MainApp: Returns result dict
    end

    MainApp->>MainApp: Updates UI with results