# UniversalMediaDownloader.spec

# -*- mode: python ; coding: utf-8 -*-
import shutil
import os

block_cipher = None

# --- Find the yt-dlp executable and add it to the binaries ---
# This is the robust way to find the entry-point script.
yt_dlp_executable_path = shutil.which('yt-dlp')
if not yt_dlp_executable_path:
    raise FileNotFoundError(
        "Could not find 'yt-dlp' executable in the system PATH. "
        "Please ensure it is installed (`pip install yt-dlp`) and accessible before building."
    )

# The binaries list tells PyInstaller to bundle this executable.
# The tuple format is ('source_path_on_your_pc', 'destination_folder_in_bundle')
# '.' means the root of the bundle, right next to your main .exe
app_binaries = [(yt_dlp_executable_path, '.')]


a = Analysis(
    ['main.py'],
    pathex=[],
    # --- USE THE BINARIES LIST DEFINED ABOVE ---
    binaries=app_binaries,
    datas=[('assets', 'assets')],
    # We still need hiddenimports for the underlying Python code
    hiddenimports=[
        'pynput.keyboard._win32',
        'pynput.keyboard._xorg',
        'pynput.keyboard._darwin',
        'yt_dlp',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='UniversalMediaDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)