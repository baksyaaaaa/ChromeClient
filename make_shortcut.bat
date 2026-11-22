@echo off
cd /d "%~dp0"
py make_shortcut.py || python make_shortcut.py
