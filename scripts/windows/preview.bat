@echo off
rem Prints a sample report to this window without Telegram (checks that quotes can be fetched).
cd /d "%~dp0..\.."
set PYTHONUTF8=1
if "%~1"=="" (
    ".venv\Scripts\python.exe" -m bot preview full --sample
) else (
    ".venv\Scripts\python.exe" -m bot preview %*
)
pause
