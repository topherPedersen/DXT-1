#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "The virtual environment is missing. Run ./install_mac.sh first."
  exit 1
fi

source .venv/bin/activate
python patch_adtof_compat.py

python worker.py &
worker_pid=$!
trap 'kill "$worker_pid" 2>/dev/null || true' EXIT INT TERM

python -m uvicorn app:app --host 127.0.0.1 --port 8000
