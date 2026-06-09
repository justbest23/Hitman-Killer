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
import ctypes.wintypes
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

# --- Death screen detection ---
# How many bright white grayscale pixels = death screen.
# Sampled at 1/3, so ~3200 expected. Raise if false positives.
WHITE_PIXEL_THRESHOLD = 1000
GRAYSCALE_TOLERANCE   = 15   # how close R/G/B must be to count as "white-gray"

# --- HUD detection (mission-started signal) ---
# During gameplay the lower-left HUD has reddish health-bar pixels
# (R≈255, G≈210, B≈207). These are absent on loading screens and menus.
# We use their presence to know a mission is active and arm auto kill.
HUD_PIXEL_THRESHOLD   = 30   # qualifying reddish pixels needed to confirm HUD
HUD_COLOR_DOMINANCE   = 20   # how much R must exceed G and B to count

# --- Scan region ---
# Bottom 25% of screen height, left 60% of width — where both the
# death screen UI and the gameplay HUD appear.
SCAN_TOP_FRACTION   = 0.75
SCAN_WIDTH_FRACTION = 0.6

# --- Timing ---
KILL_COOLDOWN = 15    # seconds to wait after a kill before re-arming
POLL_INTERVAL = 0.05  # seconds between screen checks (0.05 = 20/sec)

# ============================================================

# Auto kill state machine:
#   WAITING    — game is running but no mission detected yet (loading/menu)
#   IN_MISSION — HUD detected, auto kill is armed and watching for death
STATE_WAITING    = 'waiting'
STATE_IN_MISSION = 'in_mission'

# --- Shared state ---
auto_kill_enabled = True          # toggled from tray menu or hotkey
_tray_icon        = None          # set once the tray is running
_auto_kill_state  = STATE_WAITING # current state machine state


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


def get_game_window_rect():
    """
    Returns (left, top, width, height) of the Hitman game window, or None.
    We capture ONLY this rectangle so nothing outside the game window can
    ever trigger a false positive (e.g. dragging a white window over the
    desktop while the game is running in the background).
    """
    EnumWindows      = ctypes.windll.user32.EnumWindows
    GetWindowText    = ctypes.windll.user32.GetWindowTextW
    GetWindowTextLen = ctypes.windll.user32.GetWindowTextLengthW
    GetWindowRect    = ctypes.windll.user32.GetWindowRect
    IsWindowVisible  = ctypes.windll.user32.IsWindowVisible
    GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId

    # Build a set of PIDs belonging to the game process
    game_pids = set()
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'].lower() == game.lower():
                game_pids.add(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if not game_pids:
        return None

    found_rect = [None]

    # HWND and LPARAM are integer handles, not pointer-to-int
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def enum_callback(hwnd, lparam):
        if not IsWindowVisible(hwnd):
            return True
        pid = ctypes.c_ulong()
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in game_pids:
            return True
        # Skip tiny helper windows (splash screens, launchers)
        rect = ctypes.wintypes.RECT()
        GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right  - rect.left
        h = rect.bottom - rect.top
        if w < 400 or h < 300:
            return True
        found_rect[0] = (rect.left, rect.top, w, h)
        return False  # stop enumeration — we found the main game window

    EnumWindows(WNDENUMPROC(enum_callback), 0)
    return found_rect[0]


def count_death_pixels(raw, length):
    """
    Counts bright white perfectly-grayscale pixels.
    The MISSION FAILED overlay is full of these (R=G=B≈239).
    Gameplay HUD pixels are coloured (reddish), not grayscale.
    Stride=12 checks every 3rd pixel for speed.
    """
    count = 0
    for i in range(0, length - 3, 12):
        b = raw[i];  g = raw[i+1];  r = raw[i+2]
        if (r > 200 and g > 200 and b > 200
                and abs(r - g) < GRAYSCALE_TOLERANCE
                and abs(g - b) < GRAYSCALE_TOLERANCE):
            count += 1
    return count


def count_hud_pixels(raw, length):
    """
    Counts reddish bright pixels that indicate the gameplay HUD is visible.
    During active gameplay the health bar produces pixels around (R=255, G=210, B=207).
    On loading screens and menus the lower-left is dark — these pixels are absent.
    Once we see enough of them we know a mission is active and arm auto kill.
    """
    count = 0
    for i in range(0, length - 3, 12):
        b = raw[i];  g = raw[i+1];  r = raw[i+2]
        # Red-dominant: clearly coloured, not grayscale
        if (r > 200
                and (r - g) > HUD_COLOR_DOMINANCE
                and (r - b) > HUD_COLOR_DOMINANCE):
            count += 1
    return count


def get_game_process():
    """Returns the first running game psutil.Process, or None."""
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'].lower() == game.lower():
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


def auto_kill_loop():
    """
    Background thread — runs forever, watching for mission start then death.

    State machine:
      WAITING    — game running, no mission detected yet (loading screens, menus)
                   We look for HUD pixels (reddish health bar) to detect mission start.
      IN_MISSION — HUD was detected = mission is active.
                   We now watch for the death screen. State persists even if you
                   alt-tab; it only resets when the game process exits or we kill it.

    All screen captures are bounded to the Hitman window rectangle so that
    nothing drawn outside the game window can ever trigger a false positive.
    """
    global _auto_kill_state
    kill_until   = 0
    last_game_pid = None

    with mss.mss() as sct:
        while True:
            now = time.time()

            if now < kill_until or not auto_kill_enabled:
                time.sleep(POLL_INTERVAL)
                continue

            # --- Check game is running ---
            game_proc = get_game_process()
            if game_proc is None:
                if _auto_kill_state != STATE_WAITING:
                    log("Game exited. Resetting to waiting for next session.")
                    _auto_kill_state = STATE_WAITING
                last_game_pid = None
                time.sleep(POLL_INTERVAL)
                continue

            # Detect game restart (new PID = fresh session)
            if game_proc.pid != last_game_pid:
                if last_game_pid is not None:
                    log("Game restarted. Waiting for mission to start.")
                last_game_pid = game_proc.pid
                _auto_kill_state = STATE_WAITING

            # --- Get game window bounds (NOT the full screen) ---
            rect = get_game_window_rect()
            if rect is None:
                time.sleep(POLL_INTERVAL)
                continue

            win_left, win_top, win_w, win_h = rect

            # Only check when the game window is in the foreground.
            # If the game is minimised/behind another window we can't see the screen anyway.
            if not is_game_foreground():
                time.sleep(POLL_INTERVAL)
                continue

            # Scan region = bottom 25% of the game window, left 60% of width.
            # Both the death screen overlay and the HUD live in this area.
            scan_region = {
                "top":    win_top  + int(win_h * SCAN_TOP_FRACTION),
                "left":   win_left,
                "width":  int(win_w * SCAN_WIDTH_FRACTION),
                "height": int(win_h * (1.0 - SCAN_TOP_FRACTION)),
            }

            frame  = sct.grab(scan_region)
            raw    = frame.raw
            length = len(raw)

            # --- State machine ---
            if _auto_kill_state == STATE_WAITING:
                hud_count = count_hud_pixels(raw, length)
                if hud_count >= HUD_PIXEL_THRESHOLD:
                    log(f"Mission started (HUD pixels: {hud_count}). Auto kill armed.")
                    _auto_kill_state = STATE_IN_MISSION
                    toast("Hitman-Killer", "Auto Kill ARMED — mission detected")
                    if _tray_icon:
                        _tray_icon.update_menu()

            elif _auto_kill_state == STATE_IN_MISSION:
                death_count = count_death_pixels(raw, length)
                if death_count > WHITE_PIXEL_THRESHOLD * 0.4:
                    log(f"Death pixel count: {death_count} (threshold: {WHITE_PIXEL_THRESHOLD})")
                if death_count >= WHITE_PIXEL_THRESHOLD:
                    log(f"Death screen detected ({death_count} pixels). Killing {game}.")
                    kill_game()
                    kill_until       = now + KILL_COOLDOWN
                    _auto_kill_state = STATE_WAITING  # wait for next mission
                    if _tray_icon:
                        _tray_icon.update_menu()

            time.sleep(POLL_INTERVAL)


def toast(title, message):
    """
    Shows a small Windows balloon notification from the tray icon.
    Appears in the corner for a few seconds then disappears on its own.
    Does nothing if the tray icon isn't set up yet.
    """
    if _tray_icon:
        _tray_icon.notify(message, title)


def toggle_auto_kill(icon=None, menu_item=None):
    """Flips auto kill on/off. Called from tray menu or hotkey."""
    global auto_kill_enabled
    auto_kill_enabled = not auto_kill_enabled
    state = "ENABLED" if auto_kill_enabled else "DISABLED"
    log(f"Auto Kill {state}.")
    toast("Hitman-Killer", f"Auto Kill {state}")
    # Refresh the tray menu so the checkmark and label update
    if _tray_icon:
        _tray_icon.update_menu()


def on_quit(icon, menu_item):
    """Stops the hotkey listener and closes the tray icon."""
    log("--- Quit ---")
    keyboard.unhook_all()
    icon.stop()


def get_state_label(menu_item=None):
    """Returns the human-readable auto kill status line shown in the tray menu."""
    if not auto_kill_enabled:
        return "Auto Kill: OFF"
    if _auto_kill_state == STATE_IN_MISSION:
        return "Auto Kill: ARMED (in mission)"
    return "Auto Kill: waiting for mission..."


def setup_system_tray():
    global _tray_icon
    image = Image.open(os.path.join(_DIR, "Fancy-Logo.jpg"))

    # Right-click menu:
    #   Kill Game Now  — instant kill (same as the hotkey)
    #   Auto Kill      — checkmark toggle; label shows current detection state
    #   Quit           — exits the tray app
    menu = pystray.Menu(
        item('Kill Game Now', lambda icon, item: kill_game()),
        pystray.Menu.SEPARATOR,
        item(get_state_label, toggle_auto_kill, checked=lambda menu_item: auto_kill_enabled),
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
