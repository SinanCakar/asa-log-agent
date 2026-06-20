"""System-tray host for ASA Log Agent.

Runs the capture loop in a daemon thread started inside pystray's setup
callback — so the thread only starts after the icon is confirmed visible.
Events with severity raid/kill trigger a balloon notification.
"""
from __future__ import annotations

import os
import sys
import threading
from typing import Callable


def _load_image(here: str):
    from PIL import Image
    # Check exe folder (installer copy) then PyInstaller bundle (_MEIPASS)
    for d in [here, getattr(sys, "_MEIPASS", None)]:
        if d:
            p = os.path.join(d, "icon.png")
            if os.path.exists(p):
                return Image.open(p).convert("RGBA").resize((64, 64))
    return Image.new("RGBA", (64, 64), (243, 140, 31, 255))  # machinebot orange fallback


def run_tray(cfg: dict, here: str, run_fn: Callable, version: str) -> None:
    import pystray

    stop_event = threading.Event()
    notify_holder: list = [None]

    ALERT_SEVERITIES = {"critical", "high"}

    def on_event(ev: dict) -> None:
        fn = notify_holder[0]
        if fn and ev.get("severity") in ALERT_SEVERITIES:
            label = ev.get("category", "event").title()
            fn(ev.get("raw", "")[:120], f"ASA {label}")

    def _agent() -> None:
        run_fn(cfg, dry=False, once=False, stop_event=stop_event, notify_fn=on_event)

    def on_open_log(_icon, _item) -> None:
        log = os.path.join(here, "agent.log")
        if os.path.exists(log):
            os.startfile(log)

    def on_quit(_icon, _item) -> None:
        stop_event.set()
        _icon.stop()

    def setup(icon) -> None:
        # Called by pystray after the icon is shown — safe to start the agent now.
        icon.visible = True
        notify_holder[0] = icon.notify
        t = threading.Thread(target=_agent, daemon=True, name="asa-agent")
        t.start()

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
    icon.run(setup=setup)  # blocks until on_quit; setup fires once icon is visible
