@echo off
cd /d "%~dp0"
py -m pip install --upgrade -r requirements.txt || python -m pip install --upgrade -r requirements.txt
pause
