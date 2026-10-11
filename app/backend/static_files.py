from pathlib import Path, PureWindowsPath


def resolve_static_file(static_root: Path, full_path: str) -> Path | None:
    """只允許提供靜態根目錄內的檔案。路由參數已由 FastAPI 解碼。"""
    windows_path = PureWindowsPath(full_path)
    if windows_path.drive or windows_path.root or Path(full_path).is_absolute():
        return None
    try:
        root = static_root.resolve()
        candidate = (root / full_path.replace("\\", "/")).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return candidate
    except (OSError, ValueError, RuntimeError):
        return None
    return None
