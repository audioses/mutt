import os

# --- Argos Translate Path Fix ---
# The argostranslate library can have issues with non-ASCII user home paths.
# To prevent this, we force it to use a local, safe directory within our
# application folder by setting the ARGOS_TRANSLATE_PACKAGE_DIR environment variable.
# This is the simplest and most reliable method to control its behavior.

# Get the directory of the current script (pre_init.py)
current_dir = os.path.dirname(os.path.abspath(__file__))

# Go up one level to get the application root directory (e.g., 'instatranslate/')
app_root_dir = os.path.dirname(current_dir)

# Define the path for 'argos_models' relative to the app root. This will be
# the root directory where Argos stores its packages.
argos_models_path = os.path.join(app_root_dir, "argos_models")

# Set the environment variable. The Argos library will automatically pick this up
# on import and use it as its base directory, creating its own internal
# folder structure (like '.local/share/packages') inside it.
os.environ["ARGOS_TRANSLATE_PACKAGE_DIR"] = argos_models_path

# Ensure the directory exists so the library can write to it.
os.makedirs(argos_models_path, exist_ok=True)

print(f"[PRE_INIT] Set Argos Translate package directory to: {argos_models_path}")

# --- Hugging Face Cache Fix ---
# The huggingface_hub library defaults to ~/.cache/huggingface, which can cause
# errors on Windows with non-ASCII usernames (e.g., 'ömer').
# By setting the HF_HOME environment variable, we force it to use a safe,
# local directory within our application folder. This is the most reliable way
# to control its cache behavior globally.

# Define the path for the Hugging Face cache relative to the app root.
hf_cache_path = os.path.join(app_root_dir, "models", "hf_cache")

# Set the environment variable. All huggingface_hub operations will now use this path.
os.environ["HF_HOME"] = hf_cache_path

# Ensure the directory exists.
os.makedirs(hf_cache_path, exist_ok=True)

print(f"[PRE_INIT] Set Hugging Face home (cache) to: {hf_cache_path}")