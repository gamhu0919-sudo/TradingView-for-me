@echo off
rem Makes the bot start automatically (hidden) when you log in to Windows, then starts it now.
rem Uses your Startup folder, so no administrator rights are needed.
setlocal
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

> "%STARTUP%\PortfolioBot.vbs" echo CreateObject("WScript.Shell").Run """%~dp0start_hidden.vbs""", 0, False
if errorlevel 1 goto :fail

call "%~dp0stop_bot.bat" quiet
wscript.exe "%~dp0start_hidden.vbs"

echo.
echo Done. The bot is running in the background and will start automatically when you log in.
echo Logs: data\bot.log    Stop: stop_bot.bat    Remove auto-start: uninstall_autostart.bat
pause
exit /b 0

:fail
echo Could not write to the Startup folder: %STARTUP%
pause
exit /b 1
