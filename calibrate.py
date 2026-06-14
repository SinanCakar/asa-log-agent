#!/usr/bin/env python3
"""Region calibration for the log agent.

Default: a drag-select GUI. Captures the screen, shows it fullscreen, you drag a
rectangle over the tribe-log panel, and on release the region (x,y,w,h) is saved
to agent.ini. Falls back to a screenshot + manual coordinate entry if no GUI is
available (`--text`, or tkinter/display missing).

Usage:
    ASA_LogAgent_Calibrate.exe            # drag-select GUI
    ASA_LogAgent_Calibrate.exe --text     # manual entry
    ASA_LogAgent_Calibrate.exe --shot-only
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


def _grab_screen():
    import mss
    from PIL import Image
    with mss.mss() as sct:
        mon = sct.monitors[1]  # primary monitor
        shot = sct.grab(mon)
    return Image.frombytes("RGB", shot.size, shot.rgb)


def write_region(region: tuple[int, int, int, int]) -> None:
    cp = configparser.ConfigParser()
    cp.read(CONFIG)
    if not cp.has_section("agent"):
        cp.add_section("agent")
    cp["agent"]["region"] = ",".join(str(v) for v in region)
    with open(CONFIG, "w") as f:
        cp.write(f)
    print(f"Saved region={region} to {CONFIG}", flush=True)


def gui_select() -> tuple[int, int, int, int] | None:
    """Fullscreen drag-select over a screenshot. Returns (x,y,w,h) or None."""
    # Match physical pixels (mss) with the Tk window on high-DPI Windows.
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v2
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    import tkinter as tk
    from PIL import ImageTk

    img = _grab_screen()
    W, H = img.size
    root = tk.Tk()
    root.overrideredirect(True)
    root.geometry(f"{W}x{H}+0+0")
    root.attributes("-topmost", True)
    tkimg = ImageTk.PhotoImage(img)
    cv = tk.Canvas(root, width=W, height=H, highlightthickness=0, cursor="crosshair")
    cv.pack()
    cv.create_image(0, 0, anchor="nw", image=tkimg)
    cv.create_rectangle(0, 0, W, H, fill="black", stipple="gray25")  # dim
    cv.create_text(W // 2, 28, fill="#ffb24d", font=("Segoe UI", 18, "bold"),
                   text="Drag a box over the TRIBE-LOG panel  ·  release to save  ·  Esc to cancel")
    st = {"x0": 0, "y0": 0, "rect": None, "region": None}

    def down(e):
        st["x0"], st["y0"] = e.x, e.y

    def drag(e):
        if st["rect"]:
            cv.delete(st["rect"])
        st["rect"] = cv.create_rectangle(st["x0"], st["y0"], e.x, e.y, outline="#ff7a1a", width=3)

    def up(e):
        x, y = min(st["x0"], e.x), min(st["y0"], e.y)
        w, h = abs(e.x - st["x0"]), abs(e.y - st["y0"])
        if w > 10 and h > 10:
            st["region"] = (x, y, w, h)
            root.destroy()

    cv.bind("<Button-1>", down)
    cv.bind("<B1-Motion>", drag)
    cv.bind("<ButtonRelease-1>", up)
    root.bind("<Escape>", lambda e: root.destroy())
    root.mainloop()
    return st["region"]


def text_select(shot_only: bool) -> tuple[int, int, int, int] | None:
    shot_path = os.path.join(HERE, "calibration_screenshot.png")
    img = _grab_screen()
    img.save(shot_path)
    print("=" * 60, flush=True)
    print(f"Screenshot saved to:\n  {shot_path}", flush=True)
    print(f"(same folder as this .exe - screen {img.width}x{img.height})", flush=True)
    print("=" * 60, flush=True)
    print("Open that PNG, find the TRIBE-LOG panel, read its rectangle.", flush=True)
    if shot_only:
        return None
    print("\nEnter the panel rectangle as 4 numbers: x y width height", flush=True)
    print("Example: 150 260 950 560   (NOT the screen size)", flush=True)
    parts = input("> ").split()
    try:
        region = tuple(int(p) for p in parts)
        if len(region) != 4:
            raise ValueError
        return region
    except ValueError:
        print("\nInvalid input. Expected exactly 4 integers: x y width height", flush=True)
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", action="store_true", help="manual coordinate entry instead of GUI")
    ap.add_argument("--shot-only", action="store_true")
    args = ap.parse_args()
    region = None
    try:
        if args.text or args.shot_only:
            region = text_select(args.shot_only)
        else:
            try:
                region = gui_select()
            except Exception as e:
                print(f"GUI unavailable ({e}); falling back to manual entry.", flush=True)
                region = text_select(False)
        if region:
            write_region(region)
        elif not args.shot_only:
            print("No region selected (cancelled).", flush=True)
    except Exception as e:
        print(f"\nERROR: {e}", flush=True)
    try:
        input("\nPress Enter to close...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
