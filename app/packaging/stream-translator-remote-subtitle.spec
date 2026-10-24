# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

app_dir = Path(SPECPATH).parent
excluded_qt = [
    'QtWebEngineCore', 'QtWebEngineWidgets', 'QtWebEngineQuick',
    'QtQml', 'QtQuick', 'QtQuickWidgets', 'QtQuick3D',
    'QtMultimedia', 'QtMultimediaWidgets', 'QtPdf', 'QtPdfWidgets',
    'Qt3DCore', 'Qt3DRender', 'Qt3DInput', 'Qt3DLogic', 'Qt3DExtras', 'Qt3DAnimation',
    'QtCharts', 'QtDataVisualization', 'QtGraphs', 'QtDesigner', 'QtHelp',
    'QtSql', 'QtTest', 'QtBluetooth', 'QtNfc', 'QtPositioning', 'QtLocation',
    'QtRemoteObjects', 'QtSensors', 'QtSerialPort', 'QtSpatialAudio',
    'QtTextToSpeech', 'QtWebChannel', 'QtWebSockets', 'QtOpenGL', 'QtOpenGLWidgets',
]
a = Analysis(
    [str(app_dir / 'remote_subtitle_app.py')], pathex=[str(app_dir)],
    datas=[(str(app_dir / 'app_icon.ico'), '.')], hiddenimports=[],
    hookspath=[], hooksconfig={},
    runtime_hooks=[str(app_dir / 'packaging' / 'pyi_rth_prefer_bundled_qt.py')],
    excludes=['backend', 'fastapi', 'uvicorn', 'starlette', 'pydantic', 'torch',
              'numpy', 'yaml'] + ['PyQt6.' + name for name in excluded_qt],
    noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name='StreamTranslatorRemoteSubtitle',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
    icon=str(app_dir / 'app_icon.ico'), version=str(app_dir / 'packaging' / 'remote_subtitle_version_info.txt'),
)
