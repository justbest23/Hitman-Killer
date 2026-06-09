# ============================================================
# HITMAN-KILLER - Game Watcher
# ============================================================
# This is a background helper that runs silently (no window,
# no tray icon). It checks every 5 seconds whether your game
# is running. If it finds the game running but Kill_Hitman3.exe
# is NOT running, it pops up a warning so you know your hotkey
# won't work.
#
# Add game_watcher.exe to your Windows startup folder alongside
# Kill_Hitman3.exe so it's always watching in the background.
# ============================================================

import os     # used to find config.txt on disk
import sys    # used to cleanly exit if already running
import time   # used to pause between checks
import ctypes # used to show the Windows warning popup
import psutil # lets us see what processes are currently running

# --- Single instance lock ---
# Same idea as Kill_Hitman3.exe — prevents two copies of the watcher running.
_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "HitmanKillerWatcherMutex")
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    sys.exit(0)  # silently exit, no popup needed for a background watcher

# Figure out where this script/exe lives so we can find config.txt
_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Default settings ---
game = 'Hitman3.exe'        # the game we're watching for
tray_app = 'Kill_Hitman3.exe'  # the tray app that needs to be running

# --- Load the game name from config.txt ---
# We only need the game name here. If config.txt is missing we just
# use the default above.
try:
    with open(os.path.join(_DIR, "config.txt"), 'r') as f:
        for line in f:
            if line.startswith("game"):
                game = line.split("=", 1)[1].strip()
except FileNotFoundError:
    pass  # no config file - that's fine, we'll use the default
except Exception:
    pass  # something else went wrong reading the file - carry on anyway


# --- Helper: check if a process is currently running ---
# Pass in a process name like "Hitman3.exe" and it returns
# True if that process is running, False if it isn't.
def is_running(name):
    for proc in psutil.process_iter(['name']):
        if proc.info['name'].lower() == name.lower():
            return True
    return False


# This flag stops us from spamming the popup over and over.
# Once we've warned you for this game session, we won't warn again
# until you close the game and relaunch it.
warned = False

# --- Main loop - runs forever in the background ---
while True:
    game_running = is_running(game)
    tray_running = is_running(tray_app)

    # If the game is open but the tray app isn't, and we haven't warned yet:
    # show a Windows popup to let the user know
    if game_running and not tray_running and not warned:
        ctypes.windll.user32.MessageBoxW(
            0,
            f"{game} is running but Hitman-Killer is not!\n\nStart Kill_Hitman3.exe so your hotkey works.",
            "Hitman-Killer Warning",
            0x30  # 0x30 = warning icon (yellow triangle)
        )
        warned = True  # don't show the popup again this session

    # Once the game closes, reset the warning so it fires again next time
    elif not game_running:
        warned = False

    # Wait 5 seconds before checking again
    # (checking constantly would waste CPU for no reason)
    time.sleep(5)
