"""Runtime compatibility checks shared by staging and the standalone updater."""
import json
import re
from pathlib import Path


def read_update_json(source) -> dict:
    """Read update JSON paths or payloads consistently, including UTF-8 BOMs."""
    payload = source.read_bytes() if isinstance(source, Path) else source
    try:
        value = json.loads(payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload.lstrip("\ufeff"))
    except (ValueError, UnicodeError, AttributeError) as exc:
        raise ValueError(f"Invalid update JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Update JSON must be an object")
    return value


def validate_update_schema(document: dict) -> int:
    schema = document.get("schema")
    if type(schema) is not int or schema not in {1, 2}:
        raise RuntimeError("Unsupported update schema: expected integer 1 or 2")
    mode = document.get("update_mode")
    if schema == 2 and not mode:
        raise RuntimeError("Update schema 2 requires update_mode")
    if mode is not None and mode not in ("app_only", "runtime_replace"):
        raise RuntimeError(f"Unsupported update_mode: {mode}")
    return schema


def validate_update_runtime(manifest: dict, runtime: Path) -> None:
    minimum = manifest.get("minimum_runtime_version")
    if not minimum:  # Older packages predate this contract.
        return

    def version(value):
        if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
            raise ValueError("Invalid runtime version")
        return tuple(map(int, value.split(".")))

    try:
        info = read_update_json(runtime / "runtime-version.json")
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
