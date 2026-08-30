@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  call setup.bat || exit /b 1
)

echo Installing packaging tool...
.venv\Scripts\python.exe -m pip install --disable-pip-version-check --index-url https://pypi.org/simple -r requirements-dev.txt || goto :error

for /f "usebackq delims=" %%V in (`.venv\Scripts\python.exe -c "from fishing_assistant.constants import APP_VERSION; print(APP_VERSION)"`) do set "APP_VERSION=%%V"
if not defined APP_VERSION goto :error
set "OUTPUT_NAME=ok-MabinogiFishing-v%APP_VERSION%"

echo Building Windows executable...
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm --windowed --onefile --uac-admin --name "%OUTPUT_NAME%" --icon "fishing_assistant\assets\tomato_fish_icon.ico" --add-data "fishing_assistant\assets;fishing_assistant\assets" --collect-all pynput --collect-all mss --collect-all ok mabinogi_fishing_helper.py || goto :error

echo.
echo Build complete: dist\%OUTPUT_NAME%.exe
exit /b 0

:error
echo.
echo Build failed.
exit /b 1
