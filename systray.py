"""System-tray host for ASA Log Agent.

Runs the capture loop in a daemon thread; the tray icon lives on the main thread
(required by pystray on Windows). Events with severity raid/kill trigger a balloon
notification so the user knows something happened without opening the log.
"""
from __future__ import annotations

import os
import threading
from typing import Callable


def _load_image(here: str):
    from PIL import Image
    path = os.path.join(here, "icon.png")
    if os.path.exists(path):
        return Image.open(path).convert("RGBA").resize((64, 64))
    # Fallback: machinebot orange square
    return Image.new("RGBA", (64, 64), (243, 140, 31, 255))


def run_tray(cfg: dict, here: str, run_fn: Callable, version: str) -> None:
    import pystray

    stop_event = threading.Event()
    notify_holder: list = [None]  # filled after icon is created

    ALERT_SEVERITIES = {"critical", "high"}

    def on_event(ev: dict) -> None:
        fn = notify_holder[0]
        if fn and ev.get("severity") in ALERT_SEVERITIES:
            label = ev.get("category", "event").title()
            fn(ev.get("raw", "")[:120], f"ASA {label}")

    def _agent() -> None:
        run_fn(cfg, dry=False, once=False, stop_event=stop_event, notify_fn=on_event)

    t = threading.Thread(target=_agent, daemon=True, name="asa-agent")
    t.start()

    def on_open_log(_icon, _item) -> None:
        log = os.path.join(here, "agent.log")
        if os.path.exists(log):
            os.startfile(log)  # opens in default text viewer (Notepad on most Windows)

    def on_quit(_icon, _item) -> None:
        stop_event.set()
        _icon.stop()

    icon = pystray.Icon(
        "ASA Log Agent",
        _load_image(here),
        f"ASA Log Agent {version}",
        pystray.Menu(
            pystray.MenuItem(f"ASA Log Agent {version}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Log", on_open_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_quit),
        ),
    )
    notify_holder[0] = icon.notify
    icon.run()  # blocks until on_quit
