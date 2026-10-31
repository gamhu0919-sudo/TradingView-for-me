@echo off
rem Removes auto-start at login and stops the bot.
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if exist "%STARTUP%\PortfolioBot.vbs" del "%STARTUP%\PortfolioBot.vbs"
call "%~dp0stop_bot.bat" quiet
echo Auto-start removed and bot stopped.
pause
