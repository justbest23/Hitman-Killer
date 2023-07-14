import os
import sys
import keyboard
import psutil
import pystray
from pystray import MenuItem as item
from PIL import Image
import shutil
import winreg

## Use the variable to change the hotkey. Do this BEFORE running the "install_the_things.bat" file! ##
hotkey = 'ctrl+q'

## Use the variable to change the game you want to kill. Do this BEFORE running the "install_the_things.bat file! ##
game = 'Hitman3.exe'

def kill_game():
    # Get all running processes
    for proc in psutil.process_iter(['pid', 'name']):
        # Check if the process is Hitman3.exe
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

    # Copy the "Fancy-Logo.jpg" file to the executable directory
    shutil.copy2('Fancy-Logo.jpg', sys.argv[0])
