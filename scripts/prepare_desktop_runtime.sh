#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_VERSION="3.11.14"
PYTHON_BUILD="20260113"

case "${DXT_BUILD_ARCH:-$(uname -m)}" in
  arm64|aarch64)
    ELECTRON_ARCH="arm64"
    PYTHON_ARCH="aarch64"
    ;;
  x64|x86_64)
    ELECTRON_ARCH="x64"
    PYTHON_ARCH="x86_64"
    ;;
  *)
    echo "DXT-1 desktop releases support arm64 and x64 macOS builds only."
    exit 1
    ;;
esac

TARGET="build/runtime-${ELECTRON_ARCH}"
CACHE=".cache/desktop-runtime"
ARCHIVE_NAME="cpython-${PYTHON_VERSION}+${PYTHON_BUILD}-${PYTHON_ARCH}-apple-darwin-install_only_stripped.tar.gz"
ARCHIVE="${CACHE}/${ARCHIVE_NAME}"
URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_BUILD}/${ARCHIVE_NAME}"
FINGERPRINT="$(shasum -a 256 requirements.txt patch_adtof_compat.py scripts/prepare_desktop_runtime.sh | shasum -a 256 | awk '{print $1}')"

if [[ -x "${TARGET}/bin/python3" && -x "${TARGET}/bin/ffmpeg" && -f "${TARGET}/.dxt-runtime-${FINGERPRINT}" ]]; then
  echo "The cached DXT-1 ${ELECTRON_ARCH} runtime is current."
  exit 0
fi

mkdir -p "$CACHE" build

if [[ ! -f "$ARCHIVE" ]]; then
  echo "Downloading the redistributable Python ${PYTHON_VERSION} runtime for ${ELECTRON_ARCH}…"
  curl --fail --location --proto '=https' --tlsv1.2 "$URL" --output "${ARCHIVE}.download"
  mv "${ARCHIVE}.download" "$ARCHIVE"
fi

TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT

echo "Preparing the embedded Python environment…"
tar -xzf "$ARCHIVE" -C "$TEMP"
rm -rf "$TARGET"
mkdir -p "$TARGET"
if [[ -d "$TEMP/python/install" ]]; then
  PYTHON_SOURCE="$TEMP/python/install"
else
  PYTHON_SOURCE="$TEMP/python"
fi
ditto "$PYTHON_SOURCE" "$TARGET"

"${TARGET}/bin/python3" -m pip install --upgrade pip setuptools wheel
"${TARGET}/bin/python3" -m pip install --no-cache-dir -r requirements.txt
"${TARGET}/bin/python3" patch_adtof_compat.py

FFMPEG_PATH="$("${TARGET}/bin/python3" -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
cp "$FFMPEG_PATH" "${TARGET}/bin/ffmpeg"
chmod +x "${TARGET}/bin/python3" "${TARGET}/bin/ffmpeg"

"${TARGET}/bin/python3" -c 'import demucs, adtof_pytorch, torch, uvicorn'
"${TARGET}/bin/python3" -m demucs --help >/dev/null
"${TARGET}/bin/ffmpeg" -version >/dev/null 2>&1
touch "${TARGET}/.dxt-runtime-${FINGERPRINT}"

echo "Embedded DXT-1 runtime ready at ${TARGET}."
