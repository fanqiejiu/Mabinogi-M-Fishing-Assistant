@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  call setup.bat || exit /b 1
)

echo Installing packaging tool...
.venv\Scripts\python.exe -m pip install --disable-pip-version-check --index-url https://pypi.org/simple -r requirements-dev.txt || goto :error

echo Building Windows executable...
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm --windowed --onefile --name ok-MabinogiFishing --icon "fishing_assistant\assets\tomato_fish_icon.ico" --add-data "fishing_assistant\assets;fishing_assistant\assets" --collect-all pynput --collect-all mss --collect-all ok mabinogi_fishing_helper.py || goto :error

echo.
echo Build complete: dist\ok-MabinogiFishing.exe
exit /b 0

:error
echo.
echo Build failed.
exit /b 1
