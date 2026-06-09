# Hitman-Killer

A lightweight Windows tray app that kills a target game process when you press a hotkey — or when triggered directly from a Stream Deck button.

Works with any `.exe`, not just Hitman.

---

## Requirements

- Windows 10/11
- [Python 3.8+](https://www.digitalocean.com/community/tutorials/install-python-windows-10) (only needed to build the exe yourself)

---

## Quick Start (pre-built exe)

1. Download and unzip the latest release from the [Releases](../../releases) page
2. Edit `config.txt` to set your hotkey and target game (see [Configuration](#configuration))
3. Run `Kill_Hitman3.exe`
4. The app sits in your system tray and listens for your hotkey

---

## Build from Source

1. Install Python 3.8+
2. Open a terminal in the `Kill_Hitman` folder
3. Run `install_the_things.bat` — this installs dependencies and builds the exe
4. Your antivirus may warn about unsigned software — click **Run Anyway**
5. `Kill_Hitman3.exe` will appear in the same folder

---

## Configuration

Edit `config.txt` before running:

```
game = Hitman3.exe
hotkey = ctrl+q
```

### Hotkey options

| Format | Example | Notes |
|--------|---------|-------|
| Single key | `hotkey = F9` | Any function key or letter works |
| Ctrl combo | `hotkey = ctrl+q` | Default |
| Shift combo | `hotkey = shift+F9` | |
| Multi-modifier | `hotkey = ctrl+alt+k` | |

### Game options

Set `game` to the exact `.exe` name of the process you want to kill (case-insensitive):

```
game = Hitman3.exe
game = RDR2.exe
game = Cyberpunk2077.exe
```

---

## Stream Deck Setup

There are two ways to use a Stream Deck button.

### Method 1 — Hotkey (tray app must be running)

1. Run `Kill_Hitman3.exe` as normal (it sits in the tray)
2. In Stream Deck software, add a **Hotkey** action to a button
3. Set it to the same hotkey as in your `config.txt` (e.g. `F9`)
4. Pressing the button sends that keypress, which the tray app catches and kills the game

### Method 2 — Direct launch (no tray app needed)

The exe accepts a `--kill` flag that kills the target process immediately and exits — no tray, no hotkey listener.

1. In Stream Deck software, add an **Open** (or **System: Open**) action to a button
2. Point it to `Kill_Hitman3.exe --kill`
3. Pressing the button runs the exe, kills the game, and exits instantly

> Method 2 is recommended for Stream Deck users — it works even if the tray app isn't running.

---

## Usage

Once `Kill_Hitman3.exe` is running:

- Press your configured hotkey to kill the target process
- The tray icon tooltip shows the active hotkey (e.g. `Hitman-Killer (ctrl+q)`)
- Right-click the tray icon and select **Quit** to exit

---

## Optional: Run on Startup

To have Hitman-Killer start automatically with Windows:

1. Press `Win + R`, type `shell:startup`, press Enter
2. Create a shortcut to `Kill_Hitman3.exe` in that folder
