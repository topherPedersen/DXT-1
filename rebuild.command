#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "Stopping and removing the previous containers..."
docker compose down --remove-orphans || true

echo "Removing the previous project images..."
docker compose build --no-cache --progress=plain

echo "Starting the application..."
docker compose up
