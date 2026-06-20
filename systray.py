"""System-tray host for ASA Log Agent.

Thread model:
- Main thread: pystray message loop (required by Windows).
- setup() callback: starts the agent daemon thread after icon is visible.
- Menu callbacks: run on the pystray thread; slow ops (recalibrate, update
  check) are delegated to short-lived daemon threads.
"""
from __future__ import annotations

import configparser
import os
import subprocess
import sys
import threading
from typing import Callable


def _load_image(here: str):
    from PIL import Image
    for d in [here, getattr(sys, "_MEIPASS", None)]:
        if d:
            p = os.path.join(d, "icon.png")
            if os.path.exists(p):
                return Image.open(p).convert("RGBA").resize((64, 64))
    return Image.new("RGBA", (64, 64), (243, 140, 31, 255))


def _reload_region(cfg: dict, here: str) -> None:
    """Re-read region from agent.ini after recalibration."""
    cp = configparser.ConfigParser()
    cp.read(os.path.join(here, "agent.ini"))
    if cp.has_section("agent"):
        raw = cp["agent"].get("region", "").strip()
        if raw:
            try:
                cfg["region"] = tuple(int(v) for v in raw.split(","))
            except Exception:
                pass


def run_tray(cfg: dict, here: str, run_fn: Callable, version: str,
             startup_update: str | None = None) -> None:
    import pystray
    import updater as _updater

    stop_event = threading.Event()
    pause_event = threading.Event()   # set = paused
    notify_holder: list = [None]      # icon.notify, set after icon is visible
    update_tag: list = [startup_update]  # [version_str] or [None]

    ALERT_SEVERITIES = {"critical", "high"}

    def on_event(ev: dict) -> None:
        fn = notify_holder[0]
        if fn and ev.get("severity") in ALERT_SEVERITIES:
            fn(ev.get("raw", "")[:120], f"ASA {ev.get('category', 'event').title()}")

    def _agent() -> None:
        run_fn(cfg, dry=False, once=False,
               stop_event=stop_event, pause_event=pause_event, notify_fn=on_event)

    # ── pause / resume ────────────────────────────────────────────────────────

    def on_pause_resume(_icon, _item) -> None:
        if pause_event.is_set():
            pause_event.clear()
        else:
            pause_event.set()
        _icon.update_menu()

    def pause_label(_item) -> str:
        return "Resume" if pause_event.is_set() else "Pause"

    # ── recalibrate ───────────────────────────────────────────────────────────

    def _do_recalibrate(_icon) -> None:
        was_paused = pause_event.is_set()
        pause_event.set()
        try:
            cal = os.path.join(here, "ASA_LogAgent_Calibrate.exe")
            if os.path.exists(cal):
                subprocess.run([cal])
                _reload_region(cfg, here)
            else:
                try:
                    import calibrate as _cal
                    region = _cal.gui_select()
                    if region:
                        _cal.write_region(region)
                        cfg["region"] = region
                except Exception:
                    pass
        finally:
            if not was_paused:
                pause_event.clear()

    def on_recalibrate(_icon, _item) -> None:
        threading.Thread(target=_do_recalibrate, args=(_icon,), daemon=True).start()

    # ── open log ──────────────────────────────────────────────────────────────

    def on_open_log(_icon, _item) -> None:
        log = os.path.join(here, "agent.log")
        if os.path.exists(log):
            os.startfile(log)

    # ── updates ───────────────────────────────────────────────────────────────

    def _do_check_update(_icon) -> None:
        try:
            tag, _ = _updater.check()
            fn = notify_holder[0]
            if tag:
                update_tag[0] = tag
                _icon.update_menu()
                if fn:
                    fn(f"Version {tag} is available — open the tray menu to update.",
                       "ASA Log Agent — Update available")
            else:
                if fn:
                    fn("You are on the latest version.", "ASA Log Agent")
        except Exception:
            pass

    def on_check_update(_icon, _item) -> None:
        threading.Thread(target=_do_check_update, args=(_icon,), daemon=True).start()

    def on_install_update(_icon, _item) -> None:
        threading.Thread(target=_updater.download_and_launch, daemon=True).start()

    # ── quit ─────────────────────────────────────────────────────────────────

    def on_quit(_icon, _item) -> None:
        stop_event.set()
        _icon.stop()

    # ── menu ─────────────────────────────────────────────────────────────────

    menu = pystray.Menu(
        pystray.MenuItem(f"ASA Log Agent {version}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(pause_label, on_pause_resume),
        pystray.MenuItem("Recalibrate region", on_recalibrate),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open Log", on_open_log),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            lambda _: f"Update available: {update_tag[0]}",
            on_install_update,
            visible=lambda _: bool(update_tag[0]),
        ),
        pystray.MenuItem(
            "Check for updates",
            on_check_update,
            visible=lambda _: not update_tag[0],
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )

    def setup(icon) -> None:
        icon.visible = True
        notify_holder[0] = icon.notify
        threading.Thread(target=_agent, daemon=True, name="asa-agent").start()

    icon = pystray.Icon("ASA Log Agent", _load_image(here), f"ASA Log Agent {version}", menu)
    icon.run(setup=setup)
