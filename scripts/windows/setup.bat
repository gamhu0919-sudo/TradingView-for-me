@echo off
rem First-time setup: create virtual environment, install packages, create .env
setlocal
cd /d "%~dp0..\.."

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    set "PY=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 goto :nopython
)

".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 goto :oldpython

echo [2/3] Installing packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :fail

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [3/3] Created .env - paste your TELEGRAM_BOT_TOKEN in Notepad, then save and close.
    notepad ".env"
) else (
    echo [3/3] .env already exists.
)

echo.
echo Setup complete. Next: double-click scripts\windows\preview.bat to test.
pause
exit /b 0

:nopython
echo.
echo Python was not found. Install Python 3.10 or newer from https://www.python.org/downloads/
echo and check "Add python.exe to PATH" during installation.
pause
exit /b 1

:oldpython
echo.
echo Python 3.10 or newer is required. Install a newer Python, delete the .venv folder and run setup again.
pause
exit /b 1

:fail
echo.
echo Package installation failed. Check your internet connection and the messages above.
pause
exit /b 1
