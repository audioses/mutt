# Environment setup must happen before any other mutt imports.
from mutt import pre_init  # noqa: F401  -- side-effect: sets ARGOS/HF env vars
