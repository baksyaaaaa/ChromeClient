@echo off
title Chrome Client setup
cd /d "%~dp0"
echo.
echo  Chrome Client setup
echo  -------------------

call :findpy
if defined PY goto havepy

echo Python isn't installed yet.
where winget >nul 2>nul
if errorlevel 1 goto nopython
echo Installing Python with winget. If Windows asks, press Yes...
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
call :findpy
if not defined PY (
  rem a fresh install is not on this window's PATH yet: try its usual folder
  for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do if exist "%%D\python.exe" set "PY=%%D\python.exe"
)
if not defined PY goto nopython

:havepy
echo Using: %PY%
echo Installing the newest version of everything the launcher needs...
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto failed

echo Making a desktop shortcut...
"%PY%" make_shortcut.py --quiet

echo Starting Chrome Client...
set "PYW=%PY:python.exe=pythonw.exe%"
if /i "%PY%"=="py" set "PYW=pyw"
start "" "%PYW%" start_chrome_client.pyw
exit /b 0

:findpy
rem the "python" that Windows ships is only a Microsoft Store shortcut: really run it to see if it works
set "PY="
py -c "import sys" >nul 2>nul && (set "PY=py" & goto :eof)
python -c "import sys" >nul 2>nul && (set "PY=python" & goto :eof)
goto :eof

:nopython
echo.
echo Could not install Python automatically.
echo Opening the download page. Install it with "Add python.exe to PATH" ticked, then run setup.bat again.
start https://www.python.org/downloads/
pause
exit /b 1

:failed
echo.
echo Something went wrong while installing. Check your internet connection and run setup.bat again.
pause
exit /b 1
