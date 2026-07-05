# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for MUTT.
#
# Build:    pyinstaller --clean mutt.spec
# Output:   dist/MUTT/MUTT.exe  (onedir — recommended for wxPython + plugins)
#
# Notes:
# - GUI app: console is disabled (windowed mode).
# - Ships mutt/modes, top-level modes, format_handlers, and config.template.json
#   as real files on disk so mode_loader.py can keep using Path("mutt/modes").
# - Optional local-engine deps (torch / transformers / argostranslate) are
#   NOT bundled. If you need offline engines, install requirements-local.txt
#   and add the relevant collect_* blocks below.

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

APP_NAME = "MUTT"
ENTRY    = "main.py"


# ---------- data files ----------
# (source_on_disk, destination_inside_bundle)
datas = [
    ("mutt/modes",        "mutt/modes"),
    ("modes",             "modes"),
    ("format_handlers",   "format_handlers"),
    ("config.template.json", "."),
]

# Pick up package data that PyInstaller's default hooks may miss.
datas += collect_data_files("wx",        includes=["**/*.png", "**/*.xpm", "**/*.ico"])
datas += collect_data_files("openai")
datas += collect_data_files("google.generativeai", include_py_files=False)
datas += collect_data_files("docx")
datas += collect_data_files("pptx")
datas += collect_data_files("openpyxl")


# ---------- hidden imports ----------
hiddenimports  = []
hiddenimports += collect_submodules("format_handlers")
hiddenimports += collect_submodules("mutt")
hiddenimports += collect_submodules("google.generativeai")
hiddenimports += collect_submodules("openai")
hiddenimports += [
    "wx", "wx.adv", "wx.html", "wx.lib.scrolledpanel",
    "polib",
    "yaml",
    "requests",
    "bs4",
    "keyring", "keyring.backends.Windows",
    "openpyxl", "docx", "pptx",
    "tqdm",
]


# ---------- excludes ----------
# Keep the installer small by dropping heavy optional deps.
# Remove from this list if you need them at runtime.
excludes = [
    "torch", "torchvision", "torchaudio",
    "transformers", "huggingface_hub", "hf_xet",
    "argostranslate", "argostranslategui",
    "tkinter",
    "pytest", "pytest_mock",
    "matplotlib", "scipy", "pandas", "numpy.tests",
]


a = Analysis(
    [ENTRY],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # windowed — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # set to "assets/mutt.ico" when you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
