"""Install and verify the newest official PyPI yt-dlp (including nightly)."""
import importlib.metadata as metadata
import json
import os
import subprocess
import sys
from urllib.request import urlopen

from packaging.version import Version


def main():
    with urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=45) as response:
        index = json.load(response)
    releases = [name for name, files in index["releases"].items()
                if files and any(not item.get("yanked", False) for item in files)]
    latest = max(releases, key=Version)
    requested = os.environ.get("STREAM_TRANSLATOR_YTDLP_VERSION", latest)
    if Version(requested) != Version(latest):
        raise RuntimeError(f"Release pin {requested} differs from newest official version {latest}")
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--pre",
                    "--disable-pip-version-check", "--timeout", "20", "--retries", "2",
                    "--index-url", "https://pypi.org/simple",
                    f"yt-dlp[default]=={latest}"], check=True)
    # Use a fresh interpreter so previously imported modules cannot mask an upgrade.
    probe = "import json,importlib.metadata as m,yt_dlp,yt_dlp.version,yt_dlp_ejs;print(json.dumps({'version':m.version('yt-dlp'),'module_version':yt_dlp.version.__version__,'module':yt_dlp.__file__,'ejs':m.version('yt-dlp-ejs')}))"
    result = json.loads(subprocess.check_output([sys.executable, "-c", probe], text=True))
    if Version(result["version"]) != Version(latest) or Version(result["module_version"]).release != Version(latest).release:
        raise RuntimeError(f"yt-dlp import/version mismatch: {result}")
    print(json.dumps({"python": sys.executable, "latest": latest, **result}))


if __name__ == "__main__":
    main()
