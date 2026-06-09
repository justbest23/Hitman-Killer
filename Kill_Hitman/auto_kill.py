# ============================================================
# HITMAN-KILLER - Auto Kill (Freelancer Death Screen Detector)
# ============================================================
# This runs silently in the background alongside Kill_Hitman3.exe.
# It watches your screen and automatically kills Hitman3.exe the
# moment the Freelancer death/mission-failed screen appears.
#
# HOW IT WORKS:
#   The death screen shows a large block of bright white text/UI
#   that does NOT appear during normal gameplay. This script checks
#   the lower portion of your screen 20 times per second. If it
#   finds enough bright white grayscale pixels (the death UI),
#   it immediately kills the game process.
#
# WHY THIS IS SAFE:
#   - It only reads your screen pixels — no memory reading
#   - It only activates when Hitman3 is your active window
#   - Normal gameplay never triggers it (tested against HUD,
#     Instinct mode, and night-time maps)
#
# RUN THIS ALONGSIDE Kill_Hitman3.exe — add both to Windows startup.
# ============================================================

import os
import sys
import time
import ctypes
import psutil
import numpy as np

# mss is a fast screen-capture library — much lighter than PIL.ImageGrab
try:
    import mss
except ImportError:
    # Friendly error if mss wasn't installed
    ctypes.windll.user32.MessageBoxW(
        0,
        "Missing dependency: mss\n\nRun install_the_things.bat to fix this.",
        "Hitman-Killer Auto Kill",
        0x10
    )
    sys.exit(1)

# --- Single instance lock ---
# Prevents two copies of this watcher running at the same time
_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "HitmanKillerAutoKillMutex")
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    sys.exit(0)

_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Load settings ---
game = 'Hitman3.exe'
try:
    with open(os.path.join(_DIR, "config.txt"), 'r') as f:
        for line in f:
            if line.startswith("game"):
                game = line.split("=", 1)[1].strip()
except (FileNotFoundError, Exception):
    pass

# ============================================================
# DETECTION SETTINGS — tweak these if you get false triggers
# ============================================================

# How often to check the screen (seconds). 0.05 = 20 checks per second.
POLL_INTERVAL = 0.05

# The death screen's "MISSION FAILED" UI is full of bright white pixels
# (R > 200, G > 200, B > 200) that are perfectly grayscale (R ≈ G ≈ B).
# Normal gameplay never has more than a handful of these in the lower screen.
# We need at least this many to be confident it's the death screen.
WHITE_PIXEL_THRESHOLD = 500

# How much the R, G, B channels can differ and still count as "grayscale".
# Death screen UI is pure white-gray; normal HUD elements are coloured.
GRAYSCALE_TOLERANCE = 15

# We only scan the bottom portion of the screen where the death UI appears.
# 0.6 = bottom 40% of screen height. Left 60% of screen width.
SCAN_TOP_FRACTION = 0.75
SCAN_WIDTH_FRACTION = 0.6

# After killing the game, wait this many seconds before checking again.
# Prevents the script from going crazy if you relaunch quickly.
KILL_COOLDOWN = 15

# ============================================================


def is_game_foreground():
    """Returns True if the configured game is the currently focused window."""
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['pid'] == pid.value:
                return proc.info['name'].lower() == game.lower()
    except Exception:
        pass
    return False


def kill_game():
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'].lower() == game.lower():
            proc.kill()


def count_death_pixels(img_array):
    """
    Count pixels that look like the death screen's bright white UI elements.
    These are pixels that are:
      1. Bright (R > 200, G > 200, B > 200)
      2. Grayscale (R ≈ G ≈ B) — the death UI is white/gray, not coloured
    Normal gameplay has bright pixels but they're coloured (e.g. reddish health
    bar), so they fail the grayscale check.
    """
    r = img_array[:, :, 0].astype(np.int16)
    g = img_array[:, :, 1].astype(np.int16)
    b = img_array[:, :, 2].astype(np.int16)

    bright = (r > 200) & (g > 200) & (b > 200)
    grayscale = (
        (np.abs(r - g) < GRAYSCALE_TOLERANCE) &
        (np.abs(g - b) < GRAYSCALE_TOLERANCE) &
        (np.abs(r - b) < GRAYSCALE_TOLERANCE)
    )
    return int(np.sum(bright & grayscale))


# --- Main loop ---
kill_until = 0

with mss.mss() as sct:
    monitor = sct.monitors[1]  # primary monitor

    # Calculate the scan region once (bottom portion, left side of screen)
    scan_region = {
        "top":    monitor["top"]  + int(monitor["height"] * SCAN_TOP_FRACTION),
        "left":   monitor["left"],
        "width":  int(monitor["width"] * SCAN_WIDTH_FRACTION),
        "height": int(monitor["height"] * (1.0 - SCAN_TOP_FRACTION)),
    }

    while True:
        now = time.time()

        # Still in cooldown after a kill — skip this cycle
        if now < kill_until:
            time.sleep(POLL_INTERVAL)
            continue

        # Only scan when the game is the active window
        if not is_game_foreground():
            time.sleep(POLL_INTERVAL)
            continue

        # Grab the scan region and convert to a numpy array (very fast)
        frame = np.array(sct.grab(scan_region))

        # Count the bright grayscale pixels that signal the death screen
        death_pixels = count_death_pixels(frame)

        if death_pixels >= WHITE_PIXEL_THRESHOLD:
            kill_game()
            kill_until = now + KILL_COOLDOWN

        time.sleep(POLL_INTERVAL)
