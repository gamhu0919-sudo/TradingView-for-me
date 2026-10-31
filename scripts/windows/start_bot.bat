@echo off
rem Runs the bot and restarts it 30 seconds after it exits for any reason.
rem Logs are written to data\bot.log. Close this window (or run stop_bot.bat) to stop.
cd /d "%~dp0..\.."
set PYTHONUTF8=1
if not defined LOG_FILE set "LOG_FILE=data\bot.log"

:loop
".venv\Scripts\python.exe" -m bot
echo Bot exited (code %errorlevel%). Restarting in 30 seconds...
ping -n 31 127.0.0.1 >nul
goto loop
