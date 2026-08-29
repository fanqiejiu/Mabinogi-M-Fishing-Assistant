@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [1/2] Creating virtual environment...
  python -m venv .venv || goto :error
)

echo [2/2] Installing runtime dependencies...
.venv\Scripts\python.exe -m pip install --disable-pip-version-check --index-url https://pypi.org/simple -r requirements.txt || goto :error

echo.
echo Setup complete. Double-click run.bat to start the helper.
exit /b 0

:error
echo.
echo Setup failed. Please install Python 3.10-3.13 from python.org, then run this file again.
exit /b 1
