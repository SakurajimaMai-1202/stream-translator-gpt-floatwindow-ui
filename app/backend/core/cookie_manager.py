import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from backend.config import settings


@dataclass(frozen=True)
class CookiePlatform:
    label: str
    domains: tuple[str, ...]


COOKIE_PLATFORMS = {
    "youtube": CookiePlatform("YouTube", ("youtube.com", "youtu.be", "googlevideo.com")),
    "tiktok": CookiePlatform("TikTok", ("tiktok.com", "tiktokv.com", "tiktokcdn.com")),
    "twitter": CookiePlatform("X (Twitter)", ("x.com", "twitter.com", "twimg.com")),
    "twitch": CookiePlatform("Twitch", ("twitch.tv",)),
    "bilibili": CookiePlatform("Bilibili", ("bilibili.com", "biliapi.com")),
}

SUPPORTED_BROWSERS = {"chrome", "edge", "firefox", "brave", "chromium"}

_BROWSER_EXPORT_SCRIPT = r"""
import sys
from yt_dlp.cookies import extract_cookies_from_browser

browser, profile, output = sys.argv[1:4]
jar = extract_cookies_from_browser(browser, profile=profile or None)
jar.save(output, ignore_discard=True, ignore_expires=True)
"""


class BrowserCookieDatabaseLockedError(RuntimeError):
    pass


class BrowserCookieDecryptionUnsupportedError(RuntimeError):
    pass


def _raise_browser_export_error(browser: str, output: str) -> None:
    normalized = output.lower()
    if (
        "could not copy" in normalized and "cookie database" in normalized
    ) or "issue/7271" in normalized:
        browser_label = browser.capitalize()
        raise BrowserCookieDatabaseLockedError(
            f"{browser_label} 的 Cookies 資料庫正在使用中。請完全關閉瀏覽器"
            f"（包含背景執行的 {browser}.exe）後重試；也可以改用 Firefox。"
        )
    if "failed to decrypt" in normalized or "dpapi" in normalized:
        raise BrowserCookieDecryptionUnsupportedError(
            f"Windows 新版 {browser.capitalize()} 使用 App-Bound Encryption，"
            "yt-dlp 無法直接解密此瀏覽器的 Cookies；這不是版本過舊。"
            "請改用 Firefox，或匯入該平台的 Netscape cookies.txt。"
        )
    detail = output.strip().splitlines()
    reason = detail[-1] if detail else "瀏覽器 Cookies 匯出失敗"
    raise RuntimeError(f"無法從 {browser} 讀取 Cookies：{reason}")


def detect_cookie_platform(url: str) -> str | None:
    try:
        hostname = (urlparse(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return None
    for platform, definition in COOKIE_PLATFORMS.items():
        if any(hostname == domain or hostname.endswith(f".{domain}") for domain in definition.domains):
            return platform
    return None


def resolve_cookie_path(url: str, input_config: dict) -> str:
    platform = detect_cookie_platform(url)
    by_site = input_config.get("cookies_by_site", {})
    if platform and isinstance(by_site, dict):
        selected = str(by_site.get(platform, "") or "").strip()
        if selected:
            return selected
    return str(input_config.get("cookies", "") or "").strip()


def _resolve_runtime_python() -> Path:
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / "_runtime" / "python.exe")
    candidates.extend([
        settings.BASE_DIR / "build-runtime-cache" / "python.exe",
        settings.BASE_DIR / "build-runtime-cache" / "cpu-runtime" / "python.exe",
        Path(sys.executable),
    ])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("找不到可用的 Python runtime，無法從瀏覽器匯出 Cookies")


def _domain_matches_platform(domain: str, platform: CookiePlatform) -> bool:
    normalized = domain.strip().lower().lstrip(".")
    return any(normalized == allowed or normalized.endswith(f".{allowed}") for allowed in platform.domains)


def _filter_netscape_cookie_file(source: Path, destination: Path, platform: CookiePlatform) -> int:
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    selected = []
    for line in lines:
        if not line:
            continue
        cookie_line = line.removeprefix("#HttpOnly_")
        if cookie_line.startswith("#"):
            continue
        columns = cookie_line.split("\t")
        if len(columns) >= 7 and _domain_matches_platform(columns[0], platform):
            selected.append(line)

    if not selected:
        raise ValueError(
            f"瀏覽器中找不到 {platform.label} Cookies。請先使用所選瀏覽器登入該平台。"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_destination = destination.with_suffix(destination.suffix + ".tmp")
    content = "# Netscape HTTP Cookie File\n" + "\n".join(selected) + "\n"
    temp_destination.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temp_destination, destination)
    return len(selected)


def import_platform_cookie_file(platform: str, source: Path) -> dict:
    normalized_platform = str(platform or "").strip().lower()
    if normalized_platform not in COOKIE_PLATFORMS:
        raise ValueError(f"不支援的 Cookies 平台：{platform}")
    if not source.is_file():
        raise ValueError("找不到要匯入的 cookies.txt")

    platform_definition = COOKIE_PLATFORMS[normalized_platform]
    destination = settings.CONFIG_FILE.parent / "cookies" / f"{normalized_platform}.cookies.txt"
    cookie_count = _filter_netscape_cookie_file(source, destination, platform_definition)
    return {
        "platform": normalized_platform,
        "platform_label": platform_definition.label,
        "source": "file",
        "path": str(destination),
        "cookie_count": cookie_count,
        "updated_at": destination.stat().st_mtime,
    }


def export_platform_cookies(platform: str, browser: str, profile: str = "") -> dict:
    normalized_platform = str(platform or "").strip().lower()
    normalized_browser = str(browser or "").strip().lower()
    if normalized_platform not in COOKIE_PLATFORMS:
        raise ValueError(f"不支援的 Cookies 平台：{platform}")
    if normalized_browser not in SUPPORTED_BROWSERS:
        raise ValueError(f"不支援的瀏覽器：{browser}")

    platform_definition = COOKIE_PLATFORMS[normalized_platform]
    cookie_dir = settings.CONFIG_FILE.parent / "cookies"
    destination = cookie_dir / f"{normalized_platform}.cookies.txt"
    runtime_python = _resolve_runtime_python()

    with tempfile.TemporaryDirectory(prefix="stream-translator-cookies-") as temp_dir:
        exported = Path(temp_dir) / "browser-cookies.txt"
        process = subprocess.run(
            [
                str(runtime_python),
                "-c",
                _BROWSER_EXPORT_SCRIPT,
                normalized_browser,
                str(profile or "").strip(),
                str(exported),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if process.returncode != 0 or not exported.is_file():
            _raise_browser_export_error(
                normalized_browser,
                "\n".join(part for part in (process.stderr, process.stdout) if part),
            )
        cookie_count = _filter_netscape_cookie_file(exported, destination, platform_definition)

    return {
        "platform": normalized_platform,
        "platform_label": platform_definition.label,
        "browser": normalized_browser,
        "profile": str(profile or "").strip(),
        "path": str(destination),
        "cookie_count": cookie_count,
        "updated_at": destination.stat().st_mtime,
    }
