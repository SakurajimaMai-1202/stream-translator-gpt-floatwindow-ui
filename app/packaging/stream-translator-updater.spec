# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
app_dir = Path(SPECPATH).parent
a = Analysis([str(app_dir / 'updater.py')], pathex=[str(app_dir)], datas=[(str(app_dir/'app_icon.ico'),'.')], hiddenimports=['yaml'], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=['PyQt6.QtWebEngineCore','PyQt6.QtWebEngineWidgets'], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='StreamTranslatorUpdater', debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False, disable_windowed_traceback=False, argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None, icon=str(app_dir/'app_icon.ico'))
