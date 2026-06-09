# ============================================================
# HITMAN-KILLER - Main App
# ============================================================
# This is the main app. It sits in your system tray and:
#   - Kills the game when you press your hotkey
#   - Automatically kills the game when the Freelancer death
#     screen is detected (Auto Kill feature)
#
# Right-click the tray icon to toggle Auto Kill on/off.
# A log file (hitman_killer.log) is written next to the exe
# so you can see exactly what the app is doing.
#
# To change settings, edit config.txt.
# ============================================================

import os
import sys
import time
import argparse
import ctypes
import logging
import threading
import keyboard
import psutil
import pystray
from pystray import MenuItem as item
from PIL import Image

try:
    import mss
except ImportError:
    ctypes.windll.user32.MessageBoxW(
        0,
        "Missing dependency: mss\n\nRun install_the_things.bat to fix this.",
        "Hitman-Killer",
        0x10
    )
    sys.exit(1)

# --- Single instance lock ---
# Prevents two copies of the tray app running at once
_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "HitmanKillerTrayMutex")
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    ctypes.windll.user32.MessageBoxW(
        0,
        "Hitman-Killer is already running!\n\nCheck your system tray.",
        "Hitman-Killer",
        0x30
    )
    sys.exit(1)

# --- Path resolution ---
# sys.executable gives us the real exe location when built with PyInstaller.
# __file__ points to a temp folder in that case, so we can't use it.
if getattr(sys, 'frozen', False):
    _DIR = os.path.dirname(sys.executable)
else:
    _DIR = os.path.dirname(os.path.abspath(__file__))

# --- Logging ---
# Writes a log file next to the exe so you can see what's happening.
# Open hitman_killer.log in Notepad to diagnose any issues.
logging.basicConfig(
    filename=os.path.join(_DIR, "hitman_killer.log"),
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="[%Y-%m-%d %H:%M:%S]",
)

def log(msg):
    logging.info(msg)

# --- Default settings (used if config.txt is missing) ---
game             = 'Hitman3.exe'
hotkey           = 'ctrl+q'
auto_kill_hotkey = ''          # leave blank to disable the toggle hotkey

# --- Load settings from config.txt ---
try:
    with open(os.path.join(_DIR, "config.txt"), 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or '=' not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip()
            if key == "game":             game             = val
            elif key == "hotkey":         hotkey           = val
            elif key == "auto_kill_hotkey": auto_kill_hotkey = val
except FileNotFoundError:
    log("config.txt not found, using defaults.")
except Exception as e:
    log(f"Error reading config: {e}")

log(f"--- Started ---")
log(f"Game: {game} | Kill hotkey: {hotkey} | Auto kill hotkey: {auto_kill_hotkey or 'none'}")

# ============================================================
# AUTO KILL SETTINGS
# Tweak these if you get false positives or missed triggers.
# ============================================================

# After the game first comes into focus, wait this many seconds before
# auto kill starts watching. This prevents the loading screen / intro
# cinematics from triggering the kill.
STARTUP_DELAY = 30  # seconds after game process launches before auto kill activates

# How many bright white grayscale pixels must be on screen to trigger.
# The actual death screen produces ~3200 qualifying pixels (sampled at 1/3).
# Raise this number if you get false positives.
WHITE_PIXEL_THRESHOLD = 1000

# How much R, G, B can differ and still count as "white" (not coloured).
GRAYSCALE_TOLERANCE = 15

# Which part of the screen to scan. These are fractions of screen size.
# 0.75 = start scanning 75% down the screen (bottom quarter only).
SCAN_TOP_FRACTION   = 0.75
SCAN_WIDTH_FRACTION = 0.6

# After an auto kill, wait this long before checking again.
KILL_COOLDOWN  = 15   # seconds
POLL_INTERVAL  = 0.05 # seconds between checks (0.05 = 20 checks/sec)

# ============================================================

# --- Shared state ---
auto_kill_enabled = True   # toggled from tray menu or hotkey
_tray_icon        = None   # set once the tray is running


def kill_game():
    """Force-closes the game process. Called by hotkey or auto kill."""
    killed = False
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'].lower() == game.lower():
            proc.kill()
            killed = True
    if killed:
        log(f"Killed {game}.")
    else:
        log(f"Kill triggered but {game} was not running.")
    return killed


def is_game_foreground():
    """Returns True if the game is the currently active window."""
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    pid  = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['pid'] == pid.value:
                return proc.info['name'].lower() == game.lower()
    except Exception:
        pass
    return False


def count_death_pixels(frame):
    """
    Counts bright white perfectly-grayscale pixels in the captured frame.
    The death screen is full of these (from the MISSION FAILED overlay).
    Normal gameplay bright pixels are coloured (reddish HUD), not white-gray.

    Reads raw BGRA bytes from mss directly — no numpy needed.
    Checks every 3rd pixel (stride 12) for speed.
    """
    raw   = frame.raw  # BGRA bytes, 4 bytes per pixel
    count = 0
    for i in range(0, len(raw) - 3, 12):  # stride 12 = every 3rd pixel
        b = raw[i];  g = raw[i+1];  r = raw[i+2]
        if (r > 200 and g > 200 and b > 200
                and abs(r - g) < GRAYSCALE_TOLERANCE
                and abs(g - b) < GRAYSCALE_TOLERANCE):
            count += 1
    return count


def get_game_launch_time():
    """
    Returns the time the game process was launched, or None if it's not running.
    Using process launch time (not focus time) means alt-tabbing never resets
    the startup delay — the clock starts when the exe starts, full stop.
    """
    for proc in psutil.process_iter(['name', 'create_time']):
        try:
            if proc.info['name'].lower() == game.lower():
                return proc.info['create_time']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


def auto_kill_loop():
    """
    Background thread that watches the screen for the death screen.
    Runs forever until the app quits.
    """
    kill_until        = 0
    logged_delay_msg  = False  # avoid spamming the log with the delay message

    with mss.mss() as sct:
        monitor = sct.monitors[1]  # primary monitor
        scan_region = {
            "top":    monitor["top"]  + int(monitor["height"] * SCAN_TOP_FRACTION),
            "left":   monitor["left"],
            "width":  int(monitor["width"]  * SCAN_WIDTH_FRACTION),
            "height": int(monitor["height"] * (1.0 - SCAN_TOP_FRACTION)),
        }

        while True:
            now = time.time()

            # Skip if in cooldown after a kill, or if auto kill is disabled
            if now < kill_until or not auto_kill_enabled:
                time.sleep(POLL_INTERVAL)
                continue

            # Only check when the game is the focused window
            if not is_game_foreground():
                logged_delay_msg = False
                time.sleep(POLL_INTERVAL)
                continue

            # Check startup delay based on when the process actually launched —
            # not when it came into focus, so alt-tabbing never resets the clock
            launch_time = get_game_launch_time()
            if launch_time is None:
                time.sleep(POLL_INTERVAL)
                continue

            elapsed = now - launch_time
            if elapsed < STARTUP_DELAY:
                if not logged_delay_msg:
                    remaining = int(STARTUP_DELAY - elapsed)
                    log(f"{game} launched. Auto kill starts in ~{remaining}s "
                        f"(loading screen protection).")
                    logged_delay_msg = True
                time.sleep(POLL_INTERVAL)
                continue

            if logged_delay_msg:
                log(f"Startup delay passed. Auto kill is now active.")
                logged_delay_msg = False  # reset so it logs again if game restarts

            # Grab the screen region and count qualifying pixels
            frame       = sct.grab(scan_region)
            pixel_count = count_death_pixels(frame)

            # Log anything suspiciously high so you can diagnose false positives
            if pixel_count > WHITE_PIXEL_THRESHOLD * 0.4:
                log(f"Pixel count: {pixel_count} (threshold: {WHITE_PIXEL_THRESHOLD})")

            if pixel_count >= WHITE_PIXEL_THRESHOLD:
                log(f"Death screen detected ({pixel_count} pixels). Killing {game}.")
                kill_game()
                kill_until = now + KILL_COOLDOWN

            time.sleep(POLL_INTERVAL)


def toggle_auto_kill(icon=None, menu_item=None):
    """Flips auto kill on/off. Called from tray menu or hotkey."""
    global auto_kill_enabled
    auto_kill_enabled = not auto_kill_enabled
    state = "ENABLED" if auto_kill_enabled else "DISABLED"
    log(f"Auto Kill {state}.")
    # Refresh the tray menu so the checkmark updates
    if _tray_icon:
        _tray_icon.update_menu()


def on_quit(icon, menu_item):
    """Stops the hotkey listener and closes the tray icon."""
    log("--- Quit ---")
    keyboard.unhook_all()
    icon.stop()


def setup_system_tray():
    global _tray_icon
    image = Image.open(os.path.join(_DIR, "Fancy-Logo.jpg"))

    # Right-click menu items:
    #   Kill Game Now  — instant kill, same as pressing the hotkey
    #   Auto Kill      — checkmark toggle for the death screen watcher
    #   Quit           — closes the app
    menu = pystray.Menu(
        item('Kill Game Now', lambda icon, item: kill_game()),
        pystray.Menu.SEPARATOR,
        item('Auto Kill', toggle_auto_kill, checked=lambda menu_item: auto_kill_enabled),
        pystray.Menu.SEPARATOR,
        item('Quit', on_quit),
    )

    _tray_icon = pystray.Icon(
        "Hitman-Killer", image,
        f"Hitman-Killer ({hotkey})",
        menu
    )
    _tray_icon.run()


if __name__ == '__main__':
    # --kill flag: instantly kill the game and exit (for Stream Deck direct-launch)
    parser = argparse.ArgumentParser()
    parser.add_argument('--kill', action='store_true',
                        help='Kill the target process immediately and exit')
    args = parser.parse_args()

    if args.kill:
        kill_game()
        sys.exit(0)

    # Start the auto kill watcher in the background
    threading.Thread(target=auto_kill_loop, daemon=True).start()

    # Register hotkeys
    keyboard.add_hotkey(hotkey, kill_game)
    if auto_kill_hotkey:
        keyboard.add_hotkey(auto_kill_hotkey, toggle_auto_kill)
        log(f"Auto kill toggle hotkey registered: {auto_kill_hotkey}")

    setup_system_tray()
