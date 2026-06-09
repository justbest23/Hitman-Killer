import os
import time
import ctypes
import psutil

_DIR = os.path.dirname(os.path.abspath(__file__))

game = 'Hitman3.exe'
tray_app = 'Kill_Hitman3.exe'

try:
    with open(os.path.join(_DIR, "config.txt"), 'r') as f:
        for line in f:
            if line.startswith("game"):
                game = line.split("=", 1)[1].strip()
except FileNotFoundError:
    pass
except Exception:
    pass


def is_running(name):
    for proc in psutil.process_iter(['name']):
        if proc.info['name'].lower() == name.lower():
            return True
    return False


warned = False

while True:
    game_running = is_running(game)
    tray_running = is_running(tray_app)

    if game_running and not tray_running and not warned:
        ctypes.windll.user32.MessageBoxW(
            0,
            f"{game} is running but Hitman-Killer is not!\n\nStart Kill_Hitman3.exe so your hotkey works.",
            "Hitman-Killer Warning",
            0x30  # MB_ICONWARNING
        )
        warned = True
    elif not game_running:
        warned = False  # reset so warning fires again next session

    time.sleep(5)
