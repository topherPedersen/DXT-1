#!/bin/bash
set -e
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker Desktop is required."
  echo "Install Docker Desktop for Mac, open it, and run this file again."
  read -r -p "Press Return to close..."
  exit 1
fi

docker compose build --progress=plain
docker compose up
