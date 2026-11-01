"""
Orion — tray.py
System tray icon + global Ctrl+Space hotkey.
"""

import os
import sys
import time
import logging
import threading
import subprocess
import webbrowser
from pathlib import Path

log = logging.getLogger("orion.tray")

try:
    import pystray
    from pystray import MenuItem as Item
    from PIL import Image as PILImage
    PYSTRAY_OK = True
except ImportError:
    PYSTRAY_OK = False
    log.warning("pystray not installed — system tray unavailable")

try:
    import keyboard
    KEYBOARD_OK = True
except ImportError:
    KEYBOARD_OK = False
    log.warning("keyboard not installed — hotkey unavailable")

ORION_URL   = "http://127.0.0.1:8472"
ICON_PATH   = Path(__file__).parent.parent / "assets" / "orion_icon.png"
_icon_obj   = None
_browser_open = False


def _open_browser():
    global _browser_open
    webbrowser.open(ORION_URL)
    _browser_open = True


def _on_hotkey():
    """Called when Ctrl+Space is pressed."""
    log.debug("Ctrl+Space triggered")
    _open_browser()


def _load_tray_icon() -> "PILImage.Image | None":
    """Load the Orion icon, or create a simple purple fallback."""
    try:
        if ICON_PATH.exists():
            return PILImage.open(str(ICON_PATH)).resize((64, 64))
    except Exception:
        pass

    # Fallback: solid purple square
    try:
        img = PILImage.new("RGB", (64, 64), color=(124, 58, 237))
        return img
    except Exception:
        return None


def _quit_orion(icon, item):
    """Quit from the system tray menu."""
    log.info("Quit requested from tray")
    if icon:
        icon.stop()
    os._exit(0)


def _open_from_tray(icon, item):
    _open_browser()


def run_tray():
    """Start the system tray icon (blocking — run in a thread)."""
    if not PYSTRAY_OK:
        log.warning("Skipping tray (pystray unavailable)")
        return

    img = _load_tray_icon()
    if img is None:
        log.warning("Could not load tray icon, skipping tray")
        return

    menu = pystray.Menu(
        Item("🔭 Open Orion",  _open_from_tray, default=True),
        Item("Quit Orion",    _quit_orion),
    )

    global _icon_obj
    _icon_obj = pystray.Icon("Orion", img, "Orion Search", menu)
    log.info("System tray icon running")
    _icon_obj.run()


def register_hotkey():
    """Register Ctrl+Space global hotkey (non-blocking)."""
    if not KEYBOARD_OK:
        log.warning("Skipping hotkey (keyboard unavailable)")
        return
    try:
        keyboard.add_hotkey("ctrl+space", _on_hotkey)
        log.info("Global hotkey Ctrl+Space registered")
    except Exception as e:
        log.warning("Could not register hotkey: %s", e)


def start_tray_and_hotkey():
    """Start tray icon + hotkey in background threads."""
    hotkey_thread = threading.Thread(
        target=register_hotkey, name="orion-hotkey", daemon=True
    )
    hotkey_thread.start()

    tray_thread = threading.Thread(
        target=run_tray, name="orion-tray", daemon=True
    )
    tray_thread.start()
