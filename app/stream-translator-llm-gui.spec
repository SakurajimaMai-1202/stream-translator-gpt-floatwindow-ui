# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

# 找 PyQt6 的 Qt6 資源目錄（WebEngine 需要）
def find_qt6_dir():
    try:
        import PyQt6
        return Path(PyQt6.__file__).parent / 'Qt6'
    except Exception:
        return None

qt6_dir = find_qt6_dir()

# Qt WebEngine 必要的二進位與資源
qt_binaries = []
qt_datas = []

if qt6_dir:
    # QtWebEngineProcess.exe — Chromium 子程序
    webengine_proc = qt6_dir / 'bin' / 'QtWebEngineProcess.exe'
    if webengine_proc.exists():
        qt_binaries.append((str(webengine_proc), 'PyQt6/Qt6/bin'))

    # resources/ — Chromium ICU、pak 檔案
    resources_dir = qt6_dir / 'resources'
    if resources_dir.exists():
        qt_datas.append((str(resources_dir), 'PyQt6/Qt6/resources'))

    # translations/qtwebengine_locales/
    locales_dir = qt6_dir / 'translations' / 'qtwebengine_locales'
    if locales_dir.exists():
        qt_datas.append((str(locales_dir), 'PyQt6/Qt6/translations/qtwebengine_locales'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=qt_binaries,
    datas=[
        ('backend/static', 'backend/static'),
        ('config.example.yaml', '.'),
        ('README.txt', '.'),
        ('app_icon.ico', '.'),
    ] + qt_datas,
    hiddenimports=[
        # FastAPI / uvicorn
        'uvicorn',
        'uvicorn.lifespan.on',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.loops.auto',
        'uvicorn.logging',
        'fastapi',
        'fastapi.middleware.cors',
        'starlette',
        'starlette.routing',
        'starlette.middleware',
        'starlette.middleware.cors',
        'starlette.responses',
        'starlette.staticfiles',
        # async http (用於 probe_existing_llama_server)
        'httpx',
        'httpx._transports.default',
        'anyio',
        'anyio._backends._asyncio',
        # pydantic
        'pydantic',
        'pydantic_settings',
        # yaml
        'yaml',
        # misc
        'multipart',
        'email_validator',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude ML stack (handled by external _runtime subprocess environment)
        'torch', 'torchvision', 'torchaudio',
        'faster_whisper', 'whisper', 'openai_whisper',
        'transformers', 'tokenizers', 'safetensors',
        'onnxruntime', 'ctranslate2',
        'sklearn', 'scipy', 'numpy', 'numba', 'llvmlite',
        'librosa', 'soundfile', 'av', 'yt_dlp', 'pydub',
        'pandas', 'matplotlib',
        'tkinter', 'wx',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],                 # ← onedir 模式：binaries/datas 放在 COLLECT，不塞進 EXE
    exclude_binaries=True,
    name='Stream Translator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # ← WebEngine DLL 不壓縮，避免載入失敗
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
)

# onedir：把所有 DLL / 資源收集到同一個輸出資料夾
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Stream Translator',
)
