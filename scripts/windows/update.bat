@echo off
rem Downloads the latest code, updates packages and restarts the bot in the background.
cd /d "%~dp0..\.."
call "%~dp0stop_bot.bat" quiet
git pull
if errorlevel 1 (
    echo git pull failed. The bot was not restarted.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
wscript.exe "%~dp0start_hidden.vbs"
echo Updated and restarted.
pause
