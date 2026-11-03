@echo off
REM Run Auditly from source on Windows (needs Python 3.10+ from python.org, with "Add to PATH" ticked).
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed. Get it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  echo Setting up Auditly - first run only...
  python -m venv .venv
  .venv\Scripts\python -m pip install -q --upgrade pip
)
.venv\Scripts\python -m pip install -q -r requirements.txt
start "" .venv\Scripts\pythonw.exe run_auditly.py
