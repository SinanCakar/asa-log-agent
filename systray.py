"""System-tray host for ASA Log Agent.

Thread model:
- Main thread: pystray message loop (required by Windows).
- setup() callback: starts the agent daemon thread after icon is visible.
- Menu callbacks: run on the pystray thread; slow ops (recalibrate, update
  check, log viewer) are delegated to short-lived daemon threads.

Resilience:
- If the agent capture loop exits unexpectedly it is restarted automatically
  (stop_event not set = unintentional exit).
- If pystray's Win32 message pump exits unexpectedly (e.g. after a system
  sleep/wake or Explorer restart) the icon is recreated and run again.
- All unexpected exits are written to agent.log via the passed logf callable.
"""
from __future__ import annotations

import configparser
import os
import subprocess
import sys
import threading
import time
import traceback
from typing import Callable

# ── Windows autostart registry helpers ───────────────────────────────────────

_AUTOSTART_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_NAME = "ASA Log Agent"


def _get_autostart() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY) as k:
            winreg.QueryValueEx(k, _AUTOSTART_NAME)
            return True
    except Exception:
        return False


def _set_autostart(enable: bool) -> None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY,
                            0, winreg.KEY_SET_VALUE) as k:
            if enable:
                exe = sys.executable if getattr(sys, "frozen", False) else sys.argv[0]
                winreg.SetValueEx(k, _AUTOSTART_NAME, 0, winreg.REG_SZ, f'"{exe}"')
            else:
                try:
                    winreg.DeleteValue(k, _AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
    except Exception:
        pass

# ── Log viewer window ─────────────────────────────────────────────────────────

_SEV_COLORS = {
    "critical": "#ff5555",
    "high":     "#ffaa00",
    "medium":   "#ffdd44",
    "low":      "#88dd88",
}
_INFO_COLOR = "#999999"


def _show_log_window(here: str) -> None:
    """Open a small Tkinter window showing the last 300 lines of agent.log."""
    import re
    import tkinter as tk
    from tkinter import scrolledtext

    log_path = os.path.join(here, "agent.log")
    _sev_re  = re.compile(r"\[(critical|high|medium|low)\]")

    root = tk.Tk()
    root.title("ASA Log Agent — Event Log")
    root.geometry("800x440")
    root.configure(bg="#1e1e1e")

    txt = scrolledtext.ScrolledText(
        root, wrap=tk.WORD, state=tk.DISABLED,
        font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
        insertbackground="#d4d4d4", relief=tk.FLAT,
    )
    txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))

    for tag, color in _SEV_COLORS.items():
        txt.tag_configure(tag, foreground=color)
    txt.tag_configure("info", foreground=_INFO_COLOR)

    def refresh():
        try:
            with open(log_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-300:]
        except FileNotFoundError:
            lines = ["(agent.log not found — the agent hasn't run yet)\n"]
        txt.config(state=tk.NORMAL)
        txt.delete("1.0", tk.END)
        for line in lines:
            m   = _sev_re.search(line)
            tag = m.group(1) if m else "info"
            txt.insert(tk.END, line, tag)
        txt.config(state=tk.DISABLED)
        txt.see(tk.END)
        root.after(5000, refresh)   # auto-refresh every 5 s

    btn_frame = tk.Frame(root, bg="#1e1e1e")
    btn_frame.pack(fill=tk.X, padx=8, pady=(0, 8))

    _btn_cfg = dict(bg="#2d2d2d", fg="#d4d4d4", activebackground="#3d3d3d",
                    activeforeground="#ffffff", relief=tk.FLAT, padx=12, pady=4)
    tk.Button(btn_frame, text="Refresh now", command=refresh, **_btn_cfg).pack(side=tk.LEFT)
    tk.Button(btn_frame, text="Open raw file",
              command=lambda: os.startfile(log_path) if os.path.exists(log_path) else None,
              **_btn_cfg).pack(side=tk.LEFT, padx=6)
    tk.Button(btn_frame, text="Close", command=root.destroy, **_btn_cfg).pack(side=tk.RIGHT)

    refresh()
    root.mainloop()

# ── Icon / image ──────────────────────────────────────────────────────────────

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

# ── Main tray entry point ────────────────────────────────────────────────────

def run_tray(cfg: dict, here: str, run_fn: Callable, version: str,
             startup_update: str | None = None,
             logf: Callable[[str], None] | None = None) -> None:

    if logf is None:
        logf = lambda _msg: None   # no-op fallback if caller doesn't pass one

    import pystray
    import updater as _updater

    stop_event    = threading.Event()
    pause_event   = threading.Event()   # set = paused
    notify_holder: list = [None]        # icon.notify, set after icon is visible
    icon_holder:   list = [None]        # icon ref for tooltip updates
    update_tag:    list = [startup_update]
    agent_started: list = [False]       # guards against spawning a second agent on pystray restart

    ALERT_SEVERITIES = {"critical", "high"}

    # ── callbacks from agent thread ──────────────────────────────────────────

    def on_event(ev: dict) -> None:
        fn = notify_holder[0]
        if fn and ev.get("severity") in ALERT_SEVERITIES:
            try:
                fn(ev.get("raw", "")[:120], f"ASA {ev.get('category', 'event').title()}")
            except Exception as exc:
                logf(f"notify error (ignored): {exc!r}")

    def on_status(msg: str) -> None:
        ic = icon_holder[0]
        if ic:
            try:
                ic.title = f"ASA Log Agent {version} • {msg}"
            except Exception:
                pass

    # ── agent thread — restarts automatically if it exits without stop_event ─

    def _agent() -> None:
        while not stop_event.is_set():
            try:
                run_fn(cfg, dry=False, once=False,
                       stop_event=stop_event, pause_event=pause_event,
                       notify_fn=on_event, status_fn=on_status)
            except Exception:
                logf("AGENT CRASH:\n" + traceback.format_exc())

            if stop_event.is_set():
                break
            logf("WARNING: capture loop exited unexpectedly — restarting in 5s")
            stop_event.wait(5)

        logf("agent thread stopped")

    # ── pause / resume ────────────────────────────────────────────────────────

    def on_pause_resume(_icon, _item) -> None:
        if pause_event.is_set():
            pause_event.clear()
        else:
            pause_event.set()
        _icon.update_menu()

    def pause_label(_item) -> str:
        return "Resume" if pause_event.is_set() else "Pause"

    # ── autostart ─────────────────────────────────────────────────────────────

    def on_autostart(_icon, _item) -> None:
        _set_autostart(not _get_autostart())
        _icon.update_menu()

    # ── recalibrate ──────────────────────────────────────────────────────────

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

    # ── log viewer ────────────────────────────────────────────────────────────

    def on_view_log(_icon, _item) -> None:
        threading.Thread(target=_show_log_window, args=(here,), daemon=True).start()

    # ── updates ───────────────────────────────────────────────────────────────

    def _do_check_update(_icon) -> None:
        try:
            tag, _ = _updater.check()
            fn = notify_holder[0]
            if tag:
                update_tag[0] = tag
                _icon.update_menu()
                if fn:
                    try:
                        fn(f"Version {tag} is available — open the tray menu to update.",
                           "ASA Log Agent — Update available")
                    except Exception:
                        pass
            else:
                if fn:
                    try:
                        fn("You are on the latest version.", "ASA Log Agent")
                    except Exception:
                        pass
        except Exception:
            pass

    def on_check_update(_icon, _item) -> None:
        threading.Thread(target=_do_check_update, args=(_icon,), daemon=True).start()

    def on_install_update(_icon, _item) -> None:
        threading.Thread(target=_updater.download_and_launch, daemon=True).start()

    # ── quit ─────────────────────────────────────────────────────────────────

    def on_quit(_icon, _item) -> None:
        logf("tray: Quit clicked")
        stop_event.set()
        _icon.stop()

    # ── menu ─────────────────────────────────────────────────────────────────

    menu = pystray.Menu(
        pystray.MenuItem(f"ASA Log Agent {version}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(pause_label, on_pause_resume),
        pystray.MenuItem("Start with Windows", on_autostart,
                         checked=lambda _: _get_autostart()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Recalibrate region", on_recalibrate),
        pystray.MenuItem("View Log",           on_view_log),
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

    # CRITICAL: agent thread starts in setup() only after icon is confirmed visible.
    # agent_started guard prevents spawning a second thread if pystray restarts.
    def setup(icon) -> None:
        icon.visible    = True
        icon_holder[0]  = icon
        notify_holder[0] = icon.notify
        if not agent_started[0]:
            agent_started[0] = True
            threading.Thread(target=_agent, daemon=True, name="asa-agent").start()

    # ── pystray restart loop ──────────────────────────────────────────────────
    # If pystray's Win32 message pump exits for any reason other than on_quit
    # (e.g. Explorer restart, sleep/wake, AV interference), recreate the icon
    # and run again. The agent thread keeps running through restarts.

    tray_restarts = 0
    MAX_RESTARTS  = 10

    while not stop_event.is_set() and tray_restarts <= MAX_RESTARTS:
        icon = pystray.Icon("ASA Log Agent", _load_image(here),
                            f"ASA Log Agent {version}", menu)
        try:
            icon.run(setup=setup)
        except Exception:
            logf("pystray exception:\n" + traceback.format_exc())

        if stop_event.is_set():
            logf("tray: icon stopped cleanly")
            break

        tray_restarts += 1
        logf(f"WARNING: pystray exited without Quit (restart {tray_restarts}/{MAX_RESTARTS}) — "
             "retrying in 3s")
        icon_holder[0]   = None
        notify_holder[0] = None
        time.sleep(3)

    if tray_restarts > MAX_RESTARTS:
        logf("ERROR: pystray failed to stay alive after repeated restarts; exiting")
