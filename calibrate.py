#!/usr/bin/env python3
"""Region calibration for the log agent.

Saves a full-screen screenshot so the user can read off the pixel coordinates of
their tribe-log panel, then writes `region = x,y,w,h` back into agent.ini. A
GUI drag-select overlay can replace the manual entry later (hook kept minimal).

Usage:
    python calibrate.py            # save screenshot + prompt for coordinates
    python calibrate.py --shot-only
"""
from __future__ import annotations

import argparse
import configparser
import os
import sys


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _data_dir() -> str:
    """Writable state dir, shared with the agent: the exe folder when writable
    (single-folder install), else %LOCALAPPDATA%\\ASALogAgent fallback."""
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
CONFIG = os.path.join(HERE, "agent.ini")


def save_screenshot(path: str) -> tuple[int, int]:
    import mss
    from PIL import Image

    with mss.mss() as sct:
        mon = sct.monitors[1]  # primary monitor
        shot = sct.grab(mon)
    img = Image.frombytes("RGB", shot.size, shot.rgb)
    img.save(path)
    return img.width, img.height


def write_region(region: tuple[int, int, int, int]) -> None:
    cp = configparser.ConfigParser()
    cp.read(CONFIG)
    if not cp.has_section("agent"):
        cp.add_section("agent")
    cp["agent"]["region"] = ",".join(str(v) for v in region)
    with open(CONFIG, "w") as f:
        cp.write(f)
    print(f"Saved region={region} to {CONFIG}", flush=True)


def _run(shot_only: bool) -> None:
    shot_path = os.path.join(HERE, "calibration_screenshot.png")
    w, h = save_screenshot(shot_path)
    print("=" * 60, flush=True)
    print(f"Screenshot saved to:\n  {shot_path}", flush=True)
    print(f"(it is in the SAME folder as this .exe - screen {w}x{h})", flush=True)
    print("=" * 60, flush=True)
    print("Open that PNG, find the TRIBE-LOG panel, read its rectangle.", flush=True)
    if shot_only:
        return

    print("\nEnter the panel rectangle as 4 numbers: x y width height", flush=True)
    print("Example: 150 260 950 560   (NOT the screen size)", flush=True)
    parts = input("> ").split()
    try:
        region = tuple(int(p) for p in parts)
        if len(region) != 4:
            raise ValueError
    except ValueError:
        print("\nInvalid input. Expected exactly 4 integers: x y width height", flush=True)
        return
    write_region(region)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot-only", action="store_true")
    args = ap.parse_args()
    try:
        _run(args.shot_only)
    except Exception as e:
        print(f"\nERROR: {e}", flush=True)
    # Keep the console window open when double-clicked so output stays visible.
    try:
        input("\nPress Enter to close...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
