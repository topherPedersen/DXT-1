#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python || ! -x .venv/bin/demucs || ! -d node_modules/electron ]]; then
  echo "The desktop dependencies are missing. Run ./install_desktop_mac.sh first."
  exit 1
fi

npm start
