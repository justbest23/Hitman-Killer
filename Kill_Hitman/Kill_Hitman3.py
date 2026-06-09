import os
import keyboard
import psutil
import pystray
from pystray import MenuItem as item
from PIL import Image

_DIR = os.path.dirname(os.path.abspath(__file__))

game = 'Hitman3.exe'
hotkey = 'ctrl+q'

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


def kill_game():
    killed = False
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'].lower() == game.lower():
            proc.kill()
            killed = True
    if not killed:
        print(f"{game} is not running.")


def on_quit(icon, item):
    keyboard.unhook_all()
    icon.stop()


def setup_system_tray():
    image = Image.open(os.path.join(_DIR, "Fancy-Logo.jpg"))
    menu = (item('Quit', on_quit),)
    tray_icon = pystray.Icon("Hitman-Killer", image, f"Hitman-Killer ({hotkey})", menu)
    tray_icon.run()


if __name__ == '__main__':
    keyboard.add_hotkey(hotkey, kill_game)
    setup_system_tray()
