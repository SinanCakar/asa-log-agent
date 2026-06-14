#!/usr/bin/env python3
"""ASA Log Agent — reads the in-game ARK tribe log off the player's own screen
(OCR) and reports structured events. Anti-cheat safe: only screenshots a screen
region; never touches the game process or memory.

Flow:  mss capture(region) -> ocr -> logparse -> dedup -> offline queue -> POST

Transparency: prints every parsed event and exactly what it sends. Run with
--dry (or an empty token) to parse-and-print only, posting nothing — used for the
9.1 feasibility check on the player's real screen before any data leaves.

Config: agent.ini next to the binary (see agent.ini for keys).
"""
from __future__ import annotations

import argparse
import configparser
import difflib
import json
import os
import re
import sys
import time
import urllib.request
from collections import deque

import logparse
import ocr
import updater


def _base_dir() -> str:
    """Folder of the running program. Under a PyInstaller onefile build, this is
    the .exe folder (sys.executable), not the temp _MEIPASS extract dir."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _data_dir() -> str:
    """Writable dir for mutable state (agent.ini, offline queue, screenshot).

    Prefer keeping everything in ONE folder next to the .exe. Only if that folder
    is not writable (e.g. installed under Program Files without admin) fall back
    to %LOCALAPPDATA%\\ASALogAgent so runtime writes never fail."""
    base = _base_dir()
    try:
        probe = os.path.join(base, ".wtest")
        with open(probe, "w"):
            pass
        os.remove(probe)
        return base
    except OSError:
        if os.name == "nt":
            d = os.path.join(os.environ.get("LOCALAPPDATA", base), "ASALogAgent")
            os.makedirs(d, exist_ok=True)
            return d
        return base


HERE = _data_dir()
LOG_PATH = os.path.join(HERE, "agent.log")


def logf(msg: str) -> None:
    """Best-effort timestamped line to agent.log (next to config). Truncates if large."""
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 1_000_000:
            os.replace(LOG_PATH, LOG_PATH + ".1")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


def load_config(path: str) -> dict:
    cp = configparser.ConfigParser()
    if not cp.read(path):
        print(f"WARNING: config {path} not found; using defaults", flush=True)
    a = cp["agent"] if cp.has_section("agent") else {}
    region = None
    if a.get("region", "").strip():
        try:
            region = tuple(int(v) for v in a["region"].split(","))
            assert len(region) == 4
        except Exception:
            print("WARNING: bad region in config; calibration required", flush=True)
            region = None
    return {
        "api_url": a.get("api_url", "").strip(),  # set in agent.ini; no host hardcoded
        "token": a.get("token", "").strip(),
        "server_label": a.get("server_label", "").strip(),
        "interval": int(a.get("interval", "10")),
        "region": region,
        "fuzzy_threshold": float(a.get("fuzzy_threshold", "0.72")),
        "tesseract_path": a.get("tesseract_path", "").strip() or None,
        "queue_file": _resolve(a.get("queue_file", "offline_queue.jsonl").strip()),
        "dedup_window": int(a.get("dedup_window", "200")),
        # Similarity (0-1) above which a line counts as a duplicate of a recent one.
        # ~0.88 collapses OCR jitter of the same line without merging distinct events.
        "dedup_ratio": float(a.get("dedup_ratio", "0.88")),
    }


def _resolve(path: str) -> str:
    """Make a relative queue path absolute against the writable data dir."""
    return path if os.path.isabs(path) else os.path.join(HERE, path)


class OfflineQueue:
    """Append-only JSONL spool. Events parked here when POST fails; flushed on
    the next successful connection so nothing is lost across disconnects."""

    def __init__(self, path: str) -> None:
        self.path = path

    def add(self, events: list[dict]) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

    def drain(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
        return out

    def clear(self) -> None:
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass


def post(api_url: str, token: str, server: str, events: list[dict]) -> bool:
    """POST a batch; mirrors repl_agent.post() (Bearer token + JSON body)."""
    if not events:
        return True
    data = json.dumps({"server": server, "events": events}, ensure_ascii=False).encode()
    req = urllib.request.Request(
        api_url, data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 # Cloudflare bot protection 403s the default Python-urllib UA.
                 "User-Agent": "ASA-LogAgent/1.0"})
    try:
        r = urllib.request.urlopen(req, timeout=12)
        print(f"  POST {r.status} {r.read().decode()[:80]} ({len(events)} events)", flush=True)
        return 200 <= r.status < 300
    except Exception as e:
        print("  POST failed:", str(e)[:120], flush=True)
        return False


_NORM_RE = re.compile(r"[^a-z0-9]")


def _norm(raw: str) -> str:
    """Collapse a line to lowercase alphanumerics for OCR-tolerant comparison."""
    return _NORM_RE.sub("", raw.lower())


def run(cfg: dict, dry: bool, once: bool) -> int:
    if cfg["region"] is None:
        print("ERROR: no capture region set. Run calibrate.py first.", flush=True)
        return 2
    dry = dry or not cfg["token"] or not cfg["api_url"]
    if dry:
        print("DRY-RUN: parsing and printing only; nothing is sent.", flush=True)

    queue = OfflineQueue(cfg["queue_file"])
    recent: deque[str] = deque(maxlen=cfg["dedup_window"])

    def remember(raw: str) -> bool:
        """Fuzzy dedup: OCR re-reads the same on-screen line slightly differently
        each scan (jittered time/IDs/garbage chars), so an exact hash treats every
        read as new. Compare a normalized form to recent lines and skip near-matches."""
        n = _norm(raw)
        if not n:
            return False
        for prev in recent:
            if difflib.SequenceMatcher(None, n, prev).ratio() >= cfg["dedup_ratio"]:
                return False
        recent.append(n)
        return True

    print(f"Capturing region={cfg['region']} every {cfg['interval']}s "
          f"-> {'(dry)' if dry else cfg['api_url']}", flush=True)
    print("Keep the tribe-log panel visible. Only 'Day N, HH:MM:SS:' lines are "
          "sent. (Ctrl+C to quit)", flush=True)
    scan = 0
    while True:
        try:
            scan += 1
            img = ocr.grab_region(cfg["region"])
            text = ocr.image_to_text(img, cfg["tesseract_path"])
            events = logparse.parse_text(text, cfg["fuzzy_threshold"])
            fresh = []
            for ev in events:
                d = ev.to_dict()
                if remember(d.get("raw", "")):
                    fresh.append(d)
                    print(f"  [{ev.severity}] {ev.category}: {ev.raw}", flush=True)
            # Heartbeat so it never looks frozen: chars OCR'd / log lines / new.
            print(f"  scan #{scan}: {len(text.strip())} chars, "
                  f"{len(events)} log line(s), {len(fresh)} new", flush=True)
            if fresh and not dry:
                pending = queue.drain() + fresh
                if post(cfg["api_url"], cfg["token"], cfg["server_label"], pending):
                    queue.clear()
                else:
                    queue.add(fresh)
        except KeyboardInterrupt:
            print("\nstopped", flush=True)
            return 0
        except Exception as e:
            print("capture/parse error:", str(e)[:160], flush=True)
            logf(f"capture/parse error: {e!r}")
        if once:
            return 0
        time.sleep(cfg["interval"])


def main() -> None:
    ap = argparse.ArgumentParser(description="ASA in-game tribe-log OCR agent")
    ap.add_argument("--config", default=os.path.join(HERE, "agent.ini"))
    ap.add_argument("--dry", action="store_true", help="parse and print only; post nothing")
    ap.add_argument("--once", action="store_true", help="single capture then exit")
    ap.add_argument("--update", action="store_true", help="download + launch the latest installer")
    ap.add_argument("--no-update-check", action="store_true", help="skip the startup version check")
    args = ap.parse_args()

    print(f"ASA Log Agent {updater.__version__}", flush=True)
    logf(f"=== started {updater.__version__} (dry={args.dry}, once={args.once}) ===")
    if args.update:
        sys.exit(updater.download_and_launch())
    if not args.no_update_check:
        tag, setup = updater.check()
        if tag:
            print(f"*** UPDATE AVAILABLE: {tag} (current {updater.__version__}) ***", flush=True)
            print(f"    Update: ASA_LogAgent.exe --update   |  download: {setup}", flush=True)

    sys.exit(run(load_config(args.config), args.dry, args.once))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        import traceback
        tb = traceback.format_exc()
        logf("CRASH:\n" + tb)
        print("\n*** ERROR — details written to:", LOG_PATH, "***", flush=True)
        print(tb, flush=True)
        try:
            input("\nPress Enter to close...")  # keep window open when double-clicked
        except EOFError:
            pass
        sys.exit(1)
