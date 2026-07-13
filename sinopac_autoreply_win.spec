# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for SinoPac AutoReply (Windows .exe)."""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Playwright driver (node runtime + package)
playwright_driver = os.path.join(
    os.path.dirname(__import__('playwright').__file__), 'driver'
)

# Playwright browsers are copied after build (see post-build script)
# PyInstaller cannot process Chrome binaries, so we skip them in datas

# Hidden imports that PyInstaller misses
hidden_imports = [
    # APScheduler
    'apscheduler.schedulers.background',
    'apscheduler.triggers.interval',
    'apscheduler.triggers.date',
    'apscheduler.executors.pool',
    'apscheduler.jobstores.memory',
    # Playwright
    'playwright.sync_api',
    'playwright._impl._driver',
    # GUI
    'customtkinter',
    'CTkMessagebox',
    'CTkTable',
    'PIL',
    'PIL._tkinter_finder',
    # Data
    'openpyxl',
    'matplotlib',
    'matplotlib.backends.backend_tkagg',
    # Crypto
    'cryptography',
    'cryptography.fernet',
    # Others
    'pystray',
    'plyer',
    'plyer.platforms',
    'plyer.platforms.win',
    'plyer.platforms.win.notification',
    'greenlet',
    'pyee',
] + collect_submodules('playwright') \
  + collect_submodules('customtkinter') \
  + collect_submodules('playwright_stealth') \
  + collect_submodules('numpy') \
  + collect_submodules('matplotlib')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        (playwright_driver, 'playwright/driver'),
        ('config.py', '.'),
        ('assets', 'assets'),
    ] + collect_data_files('customtkinter')
      + collect_data_files('CTkMessagebox')
      + collect_data_files('playwright_stealth')
      + collect_data_files('matplotlib'),
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['runtime_hook_playwright.py'],
    excludes=['tkinter.test', 'unittest', 'pytest'],
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
    name='SinoPacAutoReply',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
    target_arch=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SinoPacAutoReply',
)
