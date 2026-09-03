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

rem PyInstaller resolves native DLLs from PATH. Keep only the project Python and
rem Windows system directories so unrelated tools (Poppler/libheif/FFmpeg, etc.)
rem cannot replace Qt or UCRT dependencies inside the executable.
for /f "usebackq delims=" %%P in (`.venv\Scripts\python.exe -c "import sys; print(sys.base_prefix)"`) do set "PYTHON_BASE=%%P"
if not defined PYTHON_BASE goto :error
set "PATH=%~dp0.venv\Scripts;%PYTHON_BASE%;%PYTHON_BASE%\Scripts;%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem;%SystemRoot%\System32\WindowsPowerShell\v1.0;%SystemRoot%\System32\OpenSSH"

echo Building Windows executable...
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm --windowed --onefile --uac-admin --name "%OUTPUT_NAME%" --icon "fishing_assistant\assets\tomato_fish_icon.ico" --add-data "fishing_assistant\assets;fishing_assistant\assets" --add-data "voice;voice" --collect-all pynput --collect-all mss --collect-all ok mabinogi_fishing_helper.py || goto :error

echo Verifying packaged native libraries...
.venv\Scripts\python.exe scripts\verify_windows_bundle.py --analysis "build\%OUTPUT_NAME%\Analysis-00.toc" --exe "dist\%OUTPUT_NAME%.exe" || goto :error

echo.
echo Build complete: dist\%OUTPUT_NAME%.exe
exit /b 0

:error
echo.
echo Build failed.
exit /b 1
