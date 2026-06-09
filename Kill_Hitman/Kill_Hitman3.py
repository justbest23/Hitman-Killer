# ============================================================
# HITMAN-KILLER - Main App
# ============================================================
# This is the main app. It sits in your system tray and listens
# for your hotkey. When you press the hotkey, it force-closes
# the game process instantly.
#
# To change your hotkey or target game, edit config.txt.
# ============================================================

# --- These are the tools this script needs to work ---
import os       # used to find files on your computer
import sys      # used to cleanly exit the app
import argparse # used to read command-line flags (like --kill)
import ctypes   # used to talk to Windows directly (mutex + popups)
import keyboard # listens for your hotkey in the background
import psutil   # lets us see and control running processes
import pystray  # creates the system tray icon
from pystray import MenuItem as item  # used to build the tray menu
from PIL import Image                 # used to load the tray icon image

# --- Single instance lock ---
# Creates a named mutex in Windows. If another copy of this app is already
# running, the mutex will already exist and Windows returns error 183.
# We catch that and bail out with a popup instead of launching a second copy.
_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "HitmanKillerTrayMutex")
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    ctypes.windll.user32.MessageBoxW(
        0,
        "Hitman-Killer is already running!\n\nCheck your system tray.",
        "Hitman-Killer",
        0x30  # warning icon
    )
    sys.exit(1)

# Figure out where this script/exe is located on disk.
# When built with PyInstaller (--onefile), __file__ points to a temporary
# extraction folder, not where the exe actually lives. sys.executable always
# points to the real exe, so we use that when running as a bundle.
if getattr(sys, 'frozen', False):
    _DIR = os.path.dirname(sys.executable)
else:
    _DIR = os.path.dirname(os.path.abspath(__file__))

# --- Default settings (used if config.txt is missing) ---
game = 'Hitman3.exe'  # the process name we want to kill
hotkey = 'ctrl+q'     # the keyboard shortcut that triggers the kill

# --- Load settings from config.txt ---
# We open config.txt and read the game name and hotkey from it.
# If the file doesn't exist or has a typo, we just stick with the defaults above.
try:
    with open(os.path.join(_DIR, "config.txt"), 'r') as f:
        for line in f:
            if line.startswith("game"):
                game = line.split("=", 1)[1].strip()
            elif line.startswith("hotkey"):
                hotkey = line.split("=", 1)[1].strip()
except FileNotFoundError:
    print("config.txt not found, using defaults.")
except Exception as e:
    print("Error reading config:", e)


# --- This runs when you press your hotkey ---
# It scans every running process and kills any that match the game name.
# If the game isn't running, it just prints a message (you won't see it
# unless you launch the exe from a terminal).
def kill_game():
    killed = False
    for proc in psutil.process_iter(['pid', 'name']):
        # Case-insensitive match so e.g. "hitman3.exe" still works
        if proc.info['name'].lower() == game.lower():
            proc.kill()  # force-close the process immediately
            killed = True
    if not killed:
        print(f"{game} is not running.")
    return killed


# --- This runs when you click "Quit" in the system tray ---
# It stops listening for the hotkey and closes the tray icon.
def on_quit(icon, item):
    keyboard.unhook_all()  # stop listening for the hotkey
    icon.stop()            # remove the tray icon and exit


# --- This creates and shows the system tray icon ---
# The icon sits in your taskbar tray area (bottom-right on Windows).
# The tooltip shows your active hotkey so you don't forget it.
# Right-clicking the icon gives you a Quit option.
def setup_system_tray():
    image = Image.open(os.path.join(_DIR, "Fancy-Logo.jpg"))
    menu = (item('Quit', on_quit),)
    # Tooltip text shows the active hotkey, e.g. "Hitman-Killer (ctrl+q)"
    tray_icon = pystray.Icon("Hitman-Killer", image, f"Hitman-Killer ({hotkey})", menu)
    tray_icon.run()  # this keeps the app alive in the tray


# --- Entry point - this is where the app starts ---
if __name__ == '__main__':
    # Check if the app was launched with --kill (e.g. from a Stream Deck button).
    # In that mode it kills the game immediately and exits, no tray needed.
    parser = argparse.ArgumentParser(description="Kill a game process via hotkey or on demand.")
    parser.add_argument('--kill', action='store_true', help='Kill the target process immediately and exit (use this for Stream Deck direct-launch)')
    args = parser.parse_args()

    if args.kill:
        # Stream Deck / direct-launch mode: kill and exit straight away
        kill_game()
        sys.exit(0)

    # Normal mode: register the hotkey and launch the tray icon
    keyboard.add_hotkey(hotkey, kill_game)
    setup_system_tray()
