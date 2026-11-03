@echo off
REM Build Auditly.exe (a single file that runs without Python). Output: dist\Auditly.exe
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed. Get it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe python -m venv .venv
.venv\Scripts\python build.py
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)
echo.
echo Done! Your app is in dist\Auditly.exe
explorer dist
pause
