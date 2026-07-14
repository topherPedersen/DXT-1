#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ "$#" -ne 1 ]; then
  echo "Usage: ./train.command /absolute/path/to/groove-v1.0.0"
  exit 1
fi

source .venv/bin/activate
python -m training.train \
  --dataset-root "$1" \
  --output app/models/rd8_drum_transcriber.pt
