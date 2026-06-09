@echo off
pip install -r requirements.txt
pip install -r requirements-dev.txt

pyinstaller --onefile --noconsole Kill_Hitman3.py --distpath .

pause
