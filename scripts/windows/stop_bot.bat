@echo off
rem Stops the running bot: the restart loop (start_bot.bat) and the Python process.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and ($_.CommandLine -like '*start_bot.bat*' -or ($_.Name -like 'python*' -and $_.CommandLine -like '*-m bot*')) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
if /i not "%~1"=="quiet" (
    echo Bot stopped.
    pause
)
