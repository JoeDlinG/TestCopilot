# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AITestLab (Windows packaged build).

Bundles the FastAPI backend + built frontend (static/) + plugins into a single
directory (onedir) that the NSIS installer packages into setup.exe.
"""
import os
import sys

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
# The libusb backend is only reachable on POSIX: Windows MG100 devices use the
# COMx serial path (\"connect()\" downgrades a legacy transport=usb). Bundling
# pyusb's libusb1 backend on Windows only adds dead modules to the installer.
if sys.platform != "win32":
    hiddenimports += ["usb.backend.libusb1"]
# App + restart helper
hiddenimports += ["restart_helper", "update_helper", "app", "app.main"]
# The four DC power plugins are exec'd from disk at runtime by
# plugin_service._exec_module(), so their shared transport is invisible to
# static analysis. Without an explicit hiddenimport the frozen build drops
# app.services.scpi_power_transport: every plugin import fails during the scan,
# the failure is only logged, and /api/plugins/discovered comes back empty.
hiddenimports += ["app.services.scpi_power_transport"]

# Data files: plugins (protocol drivers + manuals + skills) and the built
# frontend. These are loaded from disk at runtime (plugins via importlib, the
# frontend via StaticFiles), so PyInstaller won't auto-collect them.
datas = [
    (os.path.join(backend_dir, "plugins"), "plugins"),
    (os.path.join(backend_dir, "static"), "static"),
    # Markdown manuals for the in-app 帮助 centre (served by /api/help).
    (os.path.join(os.path.dirname(backend_dir), "docs"), "docs"),
]

# The PEAK Windows kernel driver is NOT enough for python-can: it also needs
# the user-mode PCANBasic.dll. Ship the official x64 DLL in drivers/ so a
# per-user (non-admin) install works out of the box; peakcan_plugin registers
# that directory on PATH before python-can resolves the library.
_drivers_dir = os.path.join(backend_dir, "drivers")
if sys.platform == "win32" and os.path.isdir(_drivers_dir):
    datas.append((_drivers_dir, "drivers"))

# install/ contains Linux-only udev rules and bash installers. The main
# distribution is a Windows NSIS build where they are unusable (and the
# connect-error hints must not point at them), so ship them on POSIX only.
if sys.platform != "win32":
    datas.append((os.path.join(backend_dir, "install"), "install"))

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
