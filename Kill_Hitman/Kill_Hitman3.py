import os
import sys
import keyboard
import psutil
import pystray
from pystray import MenuItem as item
from PIL import Image

# Read the config.txt file to get the game and hotkey values
config_file = os.path.join(os.getcwd(), "config.txt")

# Default values if config.txt is not found or there's an error
game = 'Hitman3.exe'
hotkey = 'ctrl+q'

try:
    with open(config_file, 'r') as f:
        config_data = f.readlines()
    for line in config_data:
        if line.startswith("game"):
            game = line.split("=")[1].strip()
        elif line.startswith("hotkey"):
            hotkey = line.split("=")[1].strip()
except FileNotFoundError:
    print("Config file not found. Using default values.")
except Exception as e:
    print("Error reading config file:", e)

def kill_game():
    # Get all running processes
    for proc in psutil.process_iter(['pid', 'name']):
        # Check if the process is the specified game
        if proc.info['name'] == game:
            # Terminate the process
            proc.kill()

def on_quit_callback(icon, item):
    keyboard.unhook_all()
    icon.stop()

def setup_system_tray():
    # Create a system tray icon
    script_dir = os.getcwd()
    image_path = os.path.join(script_dir, "Fancy-Logo.jpg")
    image = Image.open(image_path)
    menu = (item('Quit', on_quit_callback),)
    tray_icon = pystray.Icon("name", image, "Title", menu)

    # Run the system tray
    tray_icon.run()

if __name__ == '__main__':
    keyboard.add_hotkey(hotkey, kill_game)
    setup_system_tray()
