@echo off
rem Opens the bot log in Notepad.
cd /d "%~dp0..\.."
if exist "data\bot.log" (
    start "" notepad "data\bot.log"
) else (
    echo No log yet: data\bot.log
    pause
)
