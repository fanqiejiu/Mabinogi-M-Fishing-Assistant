@echo off
setlocal
cd /d "%~dp0"

rem Marker 证明依赖完整装完；解释器可能事后被防毒隔离，两者都要在。
if not exist ".venv\install-complete.marker" goto :needsetup
if not exist ".venv\Scripts\pythonw.exe" goto :needsetup
goto :launch

:needsetup
call setup.bat || exit /b 1

:launch
start "" ".venv\Scripts\pythonw.exe" "mabinogi_fishing_helper.py"
