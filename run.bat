@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\install-complete.marker" (
  call setup.bat || exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" "mabinogi_fishing_helper.py"
