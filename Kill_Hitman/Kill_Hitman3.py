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
import winsound
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
# The MISSION FAILED overlay floods the bottom-left with pure white grayscale pixels.
# Sampled at every 3rd pixel (stride 12), we expect ~3200 qualifying samples.
# Raise this number if you get false positives.
WHITE_PIXEL_THRESHOLD = 1000
GRAYSCALE_TOLERANCE   = 15   # how close R/G/B must be to count as "white-gray"

# Death screen scan = bottom 25% of game window, left 60% of width.
# The MISSION FAILED overlay sits here; the loading indicator does NOT
# (it's on the right side), so there's no cross-contamination.
DEATH_SCAN_TOP_FRAC   = 0.75
DEATH_SCAN_WIDTH_FRAC = 0.60

# --- Loading screen detection ---
# The "LOADING" text + icon is a fixed UI overlay in the bottom-right corner
# of the game window. Pixel analysis of a reference screenshot gives:
#   X: 85.2%–96.5% of width   Y: 90.1%–93.4% of height
#   ~2728 pure white (R,G,B ≈ 255) grayscale pixels
# We scan a slightly larger area for safety.
# The background image behind it changes every load, but Hitman draws a dark
# panel behind the text so the white pixels come from the UI, not the scene.
LOADING_X_FRAC          = 0.82   # scan starts at 82% from left edge
LOADING_Y_FRAC          = 0.88   # scan starts at 88% from top edge
LOADING_W_FRAC          = 0.18   # scan is 18% of window width
LOADING_H_FRAC          = 0.12   # scan is 12% of window height
LOADING_PIXEL_THRESHOLD = 150    # qualifying white pixels to confirm loading screen
                                  # (expected ~900 at stride-3 sampling; 150 is conservative)

# --- Hysteresis / grace period ---
# Require N consecutive frames of loading screen presence before entering LOADING state.
# This prevents a single bright frame (e.g. a cutscene flash) from triggering a false load.
LOADING_CONFIRM_FRAMES = 3   # consecutive frames needed to confirm loading screen

# After the loading screen disappears, wait this many seconds before arming auto kill.
# Hitman plays a short intro/spawn cinematic after loading; we don't want to fire
# during that window. 5 seconds gives it time to settle into live gameplay.
MISSION_START_DELAY = 5.0    # seconds after loading screen gone before auto kill arms

# --- Timing ---
KILL_COOLDOWN = 15    # seconds to wait after a kill before re-arming
POLL_INTERVAL = 0.05  # seconds between screen checks (0.05 = 20 checks/sec)

# ============================================================

# Auto kill state machine:
#   WAITING    — game running, watching for the loading screen to appear
#   LOADING    — loading screen detected, now waiting for it to disappear
#   IN_MISSION — loading screen gone = mission started, auto kill is armed
#
# State persists through alt-tabs; only resets when the game process exits
# or is killed.
STATE_WAITING    = 'waiting'
STATE_LOADING    = 'loading'
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


def count_loading_pixels(raw, length):
    """
    Counts pure white near-grayscale pixels that make up the "LOADING" text
    and icon in the bottom-right corner of the game window.

    Reference: 2728 qualifying pixels at R=G=B≈255 in a 286x47 px area.
    At stride-3 sampling we expect ~900; threshold is set to 150 for safety.

    The dark panel Hitman draws behind the text means these white pixels come
    from the UI overlay, not from the background image — so this works across
    all loading screen backgrounds.
    """
    count = 0
    for i in range(0, length - 3, 12):
        b = raw[i];  g = raw[i+1];  r = raw[i+2]
        if (r > 220 and g > 220 and b > 220
                and abs(r - g) < GRAYSCALE_TOLERANCE
                and abs(g - b) < GRAYSCALE_TOLERANCE):
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
    Background thread — runs forever. Implements a 3-state machine:

      WAITING    — watching the bottom-right corner for the "LOADING" text to appear.
      LOADING    — loading screen is visible; waiting for it to disappear.
      IN_MISSION — loading screen gone = mission started; watching for death screen.

    All captures are bounded to the Hitman game window (found by PID via EnumWindows),
    so content on other windows or monitors can never trigger a false positive.
    Fractions are used for all regions, so any resolution and any monitor works.

    State only resets when the game process exits or is killed — alt-tabbing
    in and out of the game does NOT affect the state.
    """
    global _auto_kill_state
    kill_until    = 0
    last_game_pid = None

    # Hysteresis / grace period tracking — see constants at top of file
    loading_seen_frames = 0
    loading_gone_since  = None  # timestamp when loading screen first disappeared

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
                    _auto_kill_state    = STATE_WAITING
                    loading_seen_frames = 0
                    loading_gone_since  = None
                    if _tray_icon:
                        _tray_icon.update_menu()
                last_game_pid = None
                time.sleep(POLL_INTERVAL)
                continue

            # Detect game restart (new PID = new session, reset state)
            if game_proc.pid != last_game_pid:
                if last_game_pid is not None:
                    log("Game restarted. Waiting for loading screen.")
                last_game_pid       = game_proc.pid
                _auto_kill_state    = STATE_WAITING
                loading_seen_frames = 0
                loading_gone_since  = None
                if _tray_icon:
                    _tray_icon.update_menu()

            # --- Find game window (works on any monitor, any position) ---
            rect = get_game_window_rect()
            if rect is None:
                time.sleep(POLL_INTERVAL)
                continue

            win_left, win_top, win_w, win_h = rect

            # Only analyse pixels when the game is in the foreground.
            # If it's minimised or hidden behind another window, the screen
            # doesn't show gameplay so there's nothing useful to check.
            if not is_game_foreground():
                time.sleep(POLL_INTERVAL)
                continue

            # --- Two separate scan regions, both relative to game window ---

            # 1. Loading indicator: bottom-right corner ("LOADING" text + icon).
            #    X: 82%-100% of window width   Y: 88%-100% of window height
            loading_region = {
                "top":    win_top  + int(win_h * LOADING_Y_FRAC),
                "left":   win_left + int(win_w * LOADING_X_FRAC),
                "width":  int(win_w * LOADING_W_FRAC),
                "height": int(win_h * LOADING_H_FRAC),
            }

            # 2. Death screen: bottom-left area (MISSION FAILED overlay).
            #    X: 0%-60% of window width     Y: 75%-100% of window height
            death_region = {
                "top":    win_top  + int(win_h * DEATH_SCAN_TOP_FRAC),
                "left":   win_left,
                "width":  int(win_w * DEATH_SCAN_WIDTH_FRAC),
                "height": int(win_h * (1.0 - DEATH_SCAN_TOP_FRAC)),
            }

            # --- State machine ---

            if _auto_kill_state == STATE_WAITING:
                # Look for the loading screen to appear
                lf     = sct.grab(loading_region)
                lcount = count_loading_pixels(lf.raw, len(lf.raw))
                if lcount >= LOADING_PIXEL_THRESHOLD:
                    loading_seen_frames += 1
                    if loading_seen_frames >= LOADING_CONFIRM_FRAMES:
                        log(f"Loading screen detected ({lcount} pixels). Waiting for it to end.")
                        _auto_kill_state   = STATE_LOADING
                        loading_gone_since = None
                        if _tray_icon:
                            _tray_icon.update_menu()
                else:
                    loading_seen_frames = 0

            elif _auto_kill_state == STATE_LOADING:
                # Loading screen confirmed visible — now wait for it to disappear,
                # then hold for MISSION_START_DELAY seconds before arming.
                lf     = sct.grab(loading_region)
                lcount = count_loading_pixels(lf.raw, len(lf.raw))
                if lcount < LOADING_PIXEL_THRESHOLD:
                    # Loading screen gone — start (or continue) the countdown
                    if loading_gone_since is None:
                        loading_gone_since = now
                        remaining = int(MISSION_START_DELAY)
                        log(f"Loading screen gone. Arming in {remaining}s.")
                    elif now - loading_gone_since >= MISSION_START_DELAY:
                        log("Auto kill ARMED.")
                        _auto_kill_state    = STATE_IN_MISSION
                        loading_seen_frames = 0
                        loading_gone_since  = None
                        toast("Hitman-Killer", "Auto Kill ARMED — mission started", beep_freq=1047)
                        if _tray_icon:
                            _tray_icon.update_menu()
                else:
                    # Loading screen reappeared — reset the gone-timer
                    loading_gone_since = None

            elif _auto_kill_state == STATE_IN_MISSION:
                # Armed — watch for the death screen in the bottom-left
                df          = sct.grab(death_region)
                death_count = count_death_pixels(df.raw, len(df.raw))
                if death_count > WHITE_PIXEL_THRESHOLD * 0.4:
                    log(f"Death pixel count: {death_count} (threshold: {WHITE_PIXEL_THRESHOLD})")
                if death_count >= WHITE_PIXEL_THRESHOLD:
                    log(f"Death screen detected ({death_count} pixels). Killing {game}.")
                    kill_game()
                    kill_until          = now + KILL_COOLDOWN
                    _auto_kill_state    = STATE_WAITING
                    loading_seen_frames = 0
                    loading_gone_since  = None
                    if _tray_icon:
                        _tray_icon.update_menu()

            time.sleep(POLL_INTERVAL)


def toast(title, message, beep_freq=880):
    """
    Plays a short beep to signal a state change.
    Audio works in any fullscreen mode and never interrupts gameplay.
    The tray menu label reflects the same state for when you do alt-tab.
    """
    def _beep():
        try:
            winsound.Beep(beep_freq, 120)
        except Exception:
            pass
    threading.Thread(target=_beep, daemon=True).start()


def toggle_auto_kill(icon=None, menu_item=None):
    """Flips auto kill on/off. Called from tray menu or hotkey."""
    global auto_kill_enabled
    auto_kill_enabled = not auto_kill_enabled
    state = "ENABLED" if auto_kill_enabled else "DISABLED"
    log(f"Auto Kill {state}.")
    toast("Hitman-Killer", f"Auto Kill {state}", beep_freq=660 if auto_kill_enabled else 330)
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
        return "Auto Kill: ARMED"
    if _auto_kill_state == STATE_LOADING:
        return "Auto Kill: loading screen..."
    return "Auto Kill: waiting for loading screen"


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
