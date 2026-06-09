# Hitman-Killer

A lightweight Windows tray app that kills a target game process when you press a hotkey — or automatically when the Freelancer death screen is detected.

Works with any `.exe`, not just Hitman.

The code has been STREAMER PROOFED, meaning I got Claude to add comments on pretty much every line so that dumbass streamers can understand that I'm not trying to kill their computers, only Hitman.exe!

---

## What's included

| File | What it does |
|------|-------------|
| `Kill_Hitman3.exe` | Sits in your system tray. Kills the game on hotkey press and auto-detects the Freelancer death screen. Right-click to toggle Auto Kill on/off. |
| `game_watcher.exe` | Runs silently in the background and warns you if the game launches without the tray app running. |

---

## Setup

### 1. Download the latest release

Go to the [Releases](../../releases/latest) page and download `Hitman-Killer.zip`. Extract it somewhere permanent (e.g. `C:\Hitman-Killer\`).

The zip contains all three pre-built exes plus `config.txt` and the logo — no Python needed.

> Your antivirus may warn about unsigned software — click **Run Anyway**. This is normal for unsigned community tools.

### 2. Configure your hotkey (optional)

Open `config.txt` and set your hotkey and target game:

```
game = Hitman3.exe
hotkey = ctrl+q
```

**Hotkey examples:**

| Format | Example |
|--------|---------|
| Single key | `hotkey = F9` |
| Ctrl combo | `hotkey = ctrl+q` |
| Shift combo | `hotkey = shift+F9` |
| Multi-modifier | `hotkey = ctrl+alt+k` |

### 5. Run the apps

Launch all three:
- `Kill_Hitman3.exe` — appears in your system tray (bottom-right)
- `game_watcher.exe` — runs silently in the background
- `auto_kill.exe` — runs silently in the background

To have them start automatically with Windows, see [Run on Startup](#run-on-startup) below.

---

## Stream Deck Setup

### Recommended — Hotkey via tray app

Run `Kill_Hitman3.exe` at startup so it sits in your tray, then bind your Stream Deck button to the same hotkey set in `config.txt`:

1. Run `Kill_Hitman3.exe` (see [Run on Startup](#run-on-startup))
2. In Stream Deck software, add a **Hotkey** action to a button
3. Set it to match your `config.txt` hotkey (e.g. `F9`)
4. Pressing the button fires the keypress, the tray app catches it and kills the game

### Alternative — Direct launch (no tray app needed)

The exe accepts a `--kill` flag that kills the target process immediately and exits.

1. In Stream Deck software, add an **Open** (or **System: Open**) action to a button
2. Point it to `Kill_Hitman3.exe --kill`
3. Pressing the button kills the game and exits instantly

---

## Run on Startup

To have all three apps start automatically with Windows:

1. Press `Win + R`, type `shell:startup`, press Enter
2. Create shortcuts to `Kill_Hitman3.exe`, `game_watcher.exe`, and `auto_kill.exe` in that folder

---

## Build from Source

If you'd rather build the exes yourself:

1. Install [Python 3.11](https://www.python.org/downloads/) — tick **"Add Python to PATH"** during install
2. Download this repo (green **Code** button → **Download ZIP**) and extract it
3. Open the `Kill_Hitman` folder and double-click `install_the_things.bat`

This installs all dependencies and builds all three exes in the same folder.
