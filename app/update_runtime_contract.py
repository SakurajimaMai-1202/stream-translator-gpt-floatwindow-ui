"""Runtime compatibility checks shared by staging and the standalone updater."""
import json
import re
from pathlib import Path


def validate_update_runtime(manifest: dict, runtime: Path) -> None:
    minimum = manifest.get("minimum_runtime_version")
    if not minimum:  # Older packages predate this contract.
        return

    def version(value):
        if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
            raise ValueError("Invalid runtime version")
        return tuple(map(int, value.split(".")))

    try:
        info = json.loads((runtime / "runtime-version.json").read_text(encoding="utf-8-sig"))
        compatible = (
            info.get("profile") == manifest.get("profile")
            and version(info.get("app_version")) >= version(minimum)
            and (runtime / "python.exe").is_file()
            and (runtime / "Lib/site-packages/omnivad/__init__.py").is_file()
        )
    except (OSError, ValueError, TypeError, AttributeError):
        compatible = False
    if not compatible:
        raise RuntimeError(
            f"此更新需要 {minimum} 或更新的同 Profile Runtime；"
            "請先安裝對應的 Full 包或包含 Runtime 的更新包。"
        )
