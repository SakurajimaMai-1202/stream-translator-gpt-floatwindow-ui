"""Offline update preparation; never replaces installed application files."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def version_tuple(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise RuntimeError(f"版本格式無效：{value}")
    return tuple(map(int, value.split(".")))


def package_parts(selected: Path) -> list[Path]:
    match = re.fullmatch(r"(.+\.zip)\.part(\d+)", selected.name, re.I)
    if not match:
        if selected.suffix.lower() != ".zip" or not selected.is_file():
            raise RuntimeError("請選取 ZIP 更新包或 .zip.part01")
        return [selected]
    if match[2] != "01":
        raise RuntimeError("分割包請選取 .part01，並將所有分割檔放在同一資料夾")
    indexed = []
    for path in selected.parent.iterdir():
        part = re.fullmatch(re.escape(match[1]) + r"\.part(\d+)", path.name, re.I)
        if part and path.is_file():
            indexed.append((int(part[1]), path))
    indexed.sort()
    if [index for index, _ in indexed] != list(range(1, len(indexed) + 1)):
        raise RuntimeError("更新分割包缺少檔案或有重複編號")
    return [path for _, path in indexed]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_package(selected: Path, app_root: Path, allowed: set[str], progress=lambda *_: None) -> Path:
    selected, app_root = selected.resolve(), app_root.resolve()
    if not (app_root / "Stream Translator.exe").is_file() or not (app_root / "config.yaml").is_file():
        raise RuntimeError("請選取含 Stream Translator.exe 與 config.yaml 的安裝目錄")
    installed = json.loads((app_root / "_runtime/runtime-version.json").read_text(encoding="utf-8-sig"))
    current_path = app_root / "app-update-build.json"
    current = json.loads(current_path.read_text(encoding="utf-8-sig")) if current_path.is_file() else {}
    current_version = str(current.get("version") or installed.get("app_version") or "")
    parts = package_parts(selected)
    checksums = {}
    for checksum_file in selected.parent.glob("SHA256SUMS*.txt"):
        for line in checksum_file.read_text(encoding="utf-8-sig").splitlines():
            match = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?(.+)", line.strip())
            if match:
                name, digest = match[2], match[1].lower()
                if name in checksums and checksums[name] != digest:
                    raise RuntimeError("目錄內存在互相矛盾的 SHA-256 清單；請保留對應版本的清單")
                checksums[name] = digest
    for part in parts:
        progress(5, f"驗證 {part.name}")
        if checksums and part.name not in checksums:
            raise RuntimeError(f"SHA-256 清單缺少 {part.name}")
        if checksums and sha256(part) != checksums[part.name]:
            raise RuntimeError(f"SHA-256 驗證失敗：{part.name}")
    if not checksums:
        progress(8, "未提供 SHA256SUMS 清單；將檢查 ZIP 完整性與套件內容")
    update_root = app_root / ".app-update"
    if update_root.is_symlink() or (update_root.exists() and update_root.resolve().parent != app_root):
        raise RuntimeError("更新暫存目錄不可指向安裝目錄外")
    update_root.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="manual-", dir=update_root))
    try:
        archive = parts[0]
        if len(parts) > 1:
            archive = work / re.sub(r"\.part01$", "", selected.name, flags=re.I)
            if shutil.disk_usage(app_root).free < sum(p.stat().st_size for p in parts):
                raise RuntimeError("磁碟空間不足，無法合併更新包")
            progress(12, "合併更新分割包")
            with archive.open("wb") as output:
                for part in parts:
                    with part.open("rb") as stream:
                        shutil.copyfileobj(stream, output, 8 * 1024 * 1024)
            if archive.name in checksums and sha256(archive) != checksums[archive.name]:
                raise RuntimeError("合併後的 ZIP SHA-256 驗證失敗")
        staging = work / "staging"
        staging.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            entries = bundle.infolist()
            seen = set()
            for entry in entries:
                name = entry.filename.replace("\\", "/")
                path = PurePosixPath(name)
                key = name.rstrip("/").casefold()
                if ("\\" in entry.filename or path.is_absolute() or not path.parts or path.parts[0] not in allowed
                        or any(p in {".", ".."} or ":" in p or p.endswith((".", " ")) for p in path.parts)
                        or any(re.fullmatch(r"(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p, re.I) for p in path.parts)
                        or stat.S_ISLNK(entry.external_attr >> 16) or key in seen):
                    raise RuntimeError(f"更新包包含不允許的路徑：{entry.filename}")
                seen.add(key)
            if shutil.disk_usage(app_root).free < sum(e.file_size for e in entries) + 256 * 1024 * 1024:
                raise RuntimeError("磁碟空間不足，無法解壓更新包")
            manifest = json.loads(bundle.read("app-update-build.json").decode("utf-8-sig"))
            if manifest.get("schema") not in {1, 2} or manifest.get("profile") != installed.get("profile"):
                raise RuntimeError("更新包格式或 CPU／CUDA／ROCm Profile 與安裝不相符")
            target_version = str(manifest.get("version") or "")
            if version_tuple(target_version) < version_tuple(current_version):
                raise RuntimeError("此更新包版本較舊，已停止降版")
            minimum = str(manifest.get("minimum_upgradable_version") or "")
            if manifest.get("requires_full_install") or (minimum and version_tuple(current_version) < version_tuple(minimum)):
                raise RuntimeError("目前版本不符合升級要求，請使用同 Profile Full 包")
            has_runtime = any(PurePosixPath(e.filename).parts[0] == "_runtime" for e in entries)
            if manifest.get("schema") == 1 and has_runtime:
                raise RuntimeError("舊式部分 Runtime 更新包不安全，請使用 Full 包")
            for index, entry in enumerate(entries):
                progress(15 + int(65 * (index + 1) / max(len(entries), 1)), "解壓並檢查更新包")
                bundle.extract(entry, staging)  # Reading each entry also verifies its CRC.
        if not (staging / "Stream Translator.exe").is_file() or not (staging / "StreamTranslatorUpdater.exe").is_file():
            raise RuntimeError("更新包缺少主程式或更新器")
        plan = {"schema": 2, "app_root": str(app_root), "staging": str(staging),
                "version": target_version, "profile": manifest["profile"],
                "update_mode": manifest.get("update_mode") or ("runtime_replace" if has_runtime else "app_only"),
                "executable": "Stream Translator.exe", "parent_pid": 0, "backend_pid": 0}
        plan_path = work / "apply-plan.json"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        progress(85, f"已準備 v{target_version}（{manifest['profile']}）；等待套用")
        return plan_path
    except Exception:
        shutil.rmtree(work)
        raise
