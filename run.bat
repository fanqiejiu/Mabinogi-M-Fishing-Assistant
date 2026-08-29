@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  call setup.bat || exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" "mabinogi_fishing_helper.py"
