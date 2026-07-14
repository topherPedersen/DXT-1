#!/usr/bin/env bash
set -euo pipefail
if ! command -v brew >/dev/null; then echo 'Install Homebrew first: https://brew.sh'; exit 1; fi
brew install python@3.11 ffmpeg
PYTHON="$(brew --prefix python@3.11)/bin/python3.11"
"$PYTHON" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
echo 'Installed. Run: source .venv/bin/activate && ./run.sh'
