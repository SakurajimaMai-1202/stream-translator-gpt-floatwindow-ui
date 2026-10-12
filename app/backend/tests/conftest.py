# Windows 上若 PyQt6／onnxruntime 等原生 DLL 先載入，torch 的 c10.dll 會初始化失敗
# (WinError 1114)，造成依測試順序而異的失敗。先行載入 torch 以固定 DLL 順序。
try:
    import torch  # noqa: F401
except Exception:
    pass


import pytest


@pytest.fixture(scope="session", autouse=True)
def isolated_log_dir(tmp_path_factory):
    log_dir = tmp_path_factory.mktemp("logs")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("STREAM_TRANSLATOR_LOG_DIR", str(log_dir))
        yield log_dir
