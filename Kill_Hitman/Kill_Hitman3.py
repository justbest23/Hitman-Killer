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

def kill_hitman3():
    # Get all running processes
    for proc in psutil.process_iter(['pid', 'name']):
        # Check if the process is Hitman3.exe
        if proc.info['name'] == 'Hitman3.exe':
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

def add_to_startup():
    # Get the current user's Startup folder path
    startup_folder = os.path.join(os.getenv('ProgramData'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')

    # Get the path to the script's executable
    script_exe = os.path.abspath(sys.argv[0])

    # Create the destination shortcut path
    shortcut_path = os.path.join(startup_folder, 'Kill_Hitman3.lnk')

    # Create a shortcut
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.TargetPath = script_exe
    shortcut.WorkingDirectory = os.getcwd()
    shortcut.IconLocation = os.path.join(os.getcwd(), 'Fancy-Logo.jpg')
    shortcut.Save()

if __name__ == '__main__':
    keyboard.add_hotkey({hotkey}, kill_hitman3)
    setup_system_tray()

    # Copy the "Fancy-Logo.jpg" file to the executable directory
    shutil.copy2('Fancy-Logo.jpg', sys.argv[0])

    # Add to Windows Startup
    add_to_startup()