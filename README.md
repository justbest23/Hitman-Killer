# Hitman-Killer

A lightweight Windows tray app that kills a target game process when you press a hotkey — or automatically when the Freelancer death screen is detected.

Works with any `.exe`, not just Hitman.

The code has been STREAMER PROOFED, meaning I got Claude to add comments on pretty much every line so that dumbass streamers can understand that I'm not trying to kill their computers, only Hitman.exe!

---

## What's included

| File | What it does |
|------|-------------|
| `Kill_Hitman3.exe` | Sits in your system tray and kills the game when you press your hotkey |
| `game_watcher.exe` | Runs in the background and warns you if the game launches without the tray app running |
| `auto_kill.exe` | Watches your screen and kills the game automatically the moment the Freelancer death screen appears |

You need to build these yourself — see below. It takes about 2 minutes.

---

## Setup

### 1. Install Python

Download and install Python 3.8 or newer from [python.org](https://www.python.org/downloads/).

> During install, tick **"Add Python to PATH"** — this is important.

### 2. Download the files

Click the green **Code** button at the top of this page → **Download ZIP**. Extract it somewhere permanent (e.g. `C:\Hitman-Killer\`).

### 3. Build the apps

Open the `Kill_Hitman` folder, then double-click `install_the_things.bat`.

This will:
- Install the required Python libraries
- Build `Kill_Hitman3.exe`, `game_watcher.exe`, and `auto_kill.exe` in the same folder

> Your antivirus may warn about unsigned software — click **Run Anyway**. This is normal for self-built Python apps.

### 4. Configure your hotkey (optional)

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
