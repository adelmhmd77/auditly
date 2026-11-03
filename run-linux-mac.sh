#!/usr/bin/env bash
# Run Auditly from source on Linux or macOS (needs Python 3.10+).
# First run creates a private virtual environment and installs dependencies.
set -e
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python 3 is not installed."
  echo "  Fedora:        sudo dnf install python3"
  echo "  Ubuntu/Debian: sudo apt install python3 python3-venv"
  echo "  macOS:         https://www.python.org/downloads/  (or: brew install python)"
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Setting up Auditly (first run only)…"
  "$PYTHON" -m venv .venv
  .venv/bin/python -m pip install -q --upgrade pip
fi
.venv/bin/python -m pip install -q -r requirements.txt
exec .venv/bin/python run_auditly.py "$@"
