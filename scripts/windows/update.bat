@echo off
rem Updates packages and restarts the bot in the background.
rem Installed with Git: also downloads the latest code (git pull).
rem Installed from ZIP: first run stop_bot.bat, extract the new ZIP over this folder, then run this file.
cd /d "%~dp0..\.."
call "%~dp0stop_bot.bat" quiet
if exist ".git" (
    git pull
    if errorlevel 1 (
        echo git pull failed. The bot was not restarted.
        pause
        exit /b 1
    )
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
wscript.exe "%~dp0start_hidden.vbs"
echo Updated and restarted.
pause
