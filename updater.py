"""Self-update check for the ASA Log Agent.

Compares the build-time version (baked into _version.py by CI) against the
latest GitHub release. Best-effort: any network/parse error is swallowed so a
failed check never blocks the agent. `--update` downloads the latest Setup.exe
and launches it (the installer preserves the existing agent.ini).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

REPO = "SinanCakar/asa-log-agent"
_API = f"https://api.github.com/repos/{REPO}/releases/latest"
_UA = "ASA-LogAgent-Updater"

try:
    from _version import __version__  # written by CI at build time
except Exception:
    __version__ = "dev"


def _ver_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v or ""))


def latest_release() -> tuple[str | None, str | None]:
    """Return (latest_tag, Setup.exe download URL) or (None, None) on failure."""
    try:
        req = urllib.request.Request(
            _API, headers={"User-Agent": _UA, "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.load(r)
        tag = data.get("tag_name")
        setup = next((a["browser_download_url"] for a in data.get("assets", [])
                      if a.get("name", "").lower().endswith("setup.exe")), None)
        return tag, setup
    except Exception:
        return None, None


def check() -> tuple[str | None, str | None]:
    """Return (newer_tag, setup_url) if an update is available, else (None, None)."""
    if __version__ == "dev":
        return None, None
    tag, setup = latest_release()
    if tag and _ver_tuple(tag) > _ver_tuple(__version__):
        return tag, setup
    return None, None


def download_and_launch() -> int:
    """Download the latest Setup.exe and launch it. Returns process exit code."""
    tag, setup = latest_release()
    if not setup:
        print("Guncelleme bulunamadi (zaten guncel olabilirsin).", flush=True)
        return 0
    import tempfile
    dst = os.path.join(tempfile.gettempdir(), "ASA_LogAgent_Setup.exe")
    print(f"Yeni surum {tag} indiriliyor...", flush=True)
    try:
        req = urllib.request.Request(setup, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
            f.write(r.read())
    except Exception as e:
        print("Indirme hatasi:", str(e)[:120], flush=True)
        return 1
    print(f"Indirildi: {dst}\nKurulum baslatiliyor (mevcut ayarlarin korunur)...", flush=True)
    if os.name == "nt":
        os.startfile(dst)  # noqa: type-ignore[attr-defined]
    else:
        print("(Windows disi: kurulumu elle calistir.)", flush=True)
    return 0
