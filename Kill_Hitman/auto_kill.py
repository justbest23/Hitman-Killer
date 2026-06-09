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

# mss is a fast screen-capture library — much lighter than PIL.ImageGrab
try:
    import mss
except ImportError:
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

if getattr(sys, 'frozen', False):
    _DIR = os.path.dirname(sys.executable)
else:
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
# Note: we sample every 3rd pixel for speed, so raw counts are scaled down ~3x.
WHITE_PIXEL_THRESHOLD = 170

# How much the R, G, B channels can differ and still count as "grayscale".
# Death screen UI is pure white-gray; normal HUD elements are coloured.
GRAYSCALE_TOLERANCE = 15

# We only scan the bottom portion of the screen where the death UI appears.
# 0.75 = scan the bottom 25% of screen height. Left 60% of screen width.
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


def count_death_pixels(frame):
    """
    Count pixels that look like the death screen's bright white UI elements.
    Works directly on the raw BGRA bytes from mss — no numpy needed.

    We check every 3rd pixel (stride of 12 bytes: 4 bytes per BGRA pixel x 3)
    to keep CPU usage low. The death screen has ~9700 qualifying pixels so
    even at 1/3 sampling we're well above the threshold.

    Qualifying pixel:
      - Bright:    R > 200, G > 200, B > 200
      - Grayscale: R ≈ G ≈ B (channels within GRAYSCALE_TOLERANCE of each other)
    Normal gameplay's bright pixels are coloured (e.g. reddish health bar)
    so they fail the grayscale check.
    """
    raw = frame.raw   # BGRA bytes — 4 bytes per pixel
    count = 0
    # Stride of 12 = skip 2 pixels each step (4 bytes/pixel x 3)
    for i in range(0, len(raw) - 3, 12):
        b = raw[i]
        g = raw[i + 1]
        r = raw[i + 2]
        if (r > 200 and g > 200 and b > 200
                and abs(r - g) < GRAYSCALE_TOLERANCE
                and abs(g - b) < GRAYSCALE_TOLERANCE):
            count += 1
    return count


# --- Main loop ---
kill_until = 0

with mss.mss() as sct:
    monitor = sct.monitors[1]  # primary monitor

    # Calculate the scan region once (bottom 25%, left 60% of screen)
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

        # Grab the scan region (raw BGRA bytes, no conversion needed)
        frame = sct.grab(scan_region)

        # Count the bright grayscale pixels that signal the death screen
        if count_death_pixels(frame) >= WHITE_PIXEL_THRESHOLD:
            kill_game()
            kill_until = now + KILL_COOLDOWN

        time.sleep(POLL_INTERVAL)
