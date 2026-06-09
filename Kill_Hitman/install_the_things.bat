@echo off
pip install -r requirements.txt
pip install -r requirements-dev.txt

pyinstaller --onefile --noconsole Kill_Hitman3.py --distpath .
pyinstaller --onefile --noconsole game_watcher.py --distpath .
pyinstaller --onefile --noconsole auto_kill.py --distpath .

pause
