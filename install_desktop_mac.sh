#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")"

if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js and npm are required. Install the current Node.js LTS release from https://nodejs.org/ and run this script again."
  exit 1
fi

./install_mac.sh
npm install

echo
echo "DXT-1 desktop setup is complete. Start it with:"
echo "  ./run_desktop_mac.sh"
