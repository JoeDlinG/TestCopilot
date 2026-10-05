# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AITestLab (Windows packaged build).

Bundles the FastAPI backend + built frontend (static/) + plugins into a single
directory (onedir) that the NSIS installer packages into setup.exe.
"""
import os

from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_data_files,
)

block_cipher = None

# Backend root (this file lives in backend/).
try:
    backend_dir = SPECPATH
except NameError:
    backend_dir = os.path.abspath(os.getcwd())

hiddenimports = []
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("fastapi")
hiddenimports += collect_submodules("sqlalchemy")
hiddenimports += collect_submodules("pydantic")
hiddenimports += collect_submodules("anyio")
hiddenimports += collect_submodules("httpcore")
hiddenimports += collect_submodules("httpx")
# SQLAlchemy loads its DBAPI dialect dynamically (from the URL's "+aiosqlite").
hiddenimports += ["aiosqlite", "greenlet"]
hiddenimports += ["sqlalchemy.dialects.sqlite.aiosqlite", "sqlalchemy.dialects.sqlite.pysqlite"]
# SCPI/VISA: ensure the pure-Python backend is bundled (entry-point discovery
# is unreliable in frozen builds).
hiddenimports += collect_submodules("pyvisa")
hiddenimports += collect_submodules("pyvisa_py")
hiddenimports += ["pyvisa_py"]
# CAN / serial / USB
hiddenimports += collect_submodules("can")
hiddenimports += ["serial.serialwin32", "serial.tools.list_ports_windows"]
hiddenimports += ["usb.backend.libusb1"]
# App + restart helper
hiddenimports += ["restart_helper", "app", "app.main"]

# Data files: plugins (protocol drivers + manuals + skills) and the built
# frontend. These are loaded from disk at runtime (plugins via importlib, the
# frontend via StaticFiles), so PyInstaller won't auto-collect them.
datas = [
    (os.path.join(backend_dir, "plugins"), "plugins"),
    (os.path.join(backend_dir, "static"), "static"),
]

a = Analysis(
    [os.path.join(backend_dir, "run.py")],
    pathex=[backend_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest", "pytest"],
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
    name="AITestLab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(backend_dir, "static", "aitestlab.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AITestLab",
)
