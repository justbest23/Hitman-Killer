@echo off
pip install -r requirements.txt

pyinstaller --onefile --noconsole Kill_Hitman3.py --distpath .

pause