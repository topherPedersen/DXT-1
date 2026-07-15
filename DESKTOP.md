# DXT-1 macOS Desktop Guide

DXT-1 now runs as an Electron desktop application. Audio conversion happens
locally on the Mac, so a DigitalOcean server is not required and uploaded songs
never need to leave the computer.

## Run the desktop app from this repository

Requirements:

- macOS 12 or newer
- Node.js and npm (the current LTS release is recommended)
- Python 3.9 or newer
- Homebrew, used by the installer to install FFmpeg when necessary
- An internet connection during installation and the first conversion

In Terminal, change to the cloned DXT-1 directory and run:

```bash
chmod +x install_desktop_mac.sh run_desktop_mac.sh
./install_desktop_mac.sh
./run_desktop_mac.sh
```

The first command installs the existing Python conversion environment and the
Electron development dependencies. Later launches only need
`./run_desktop_mac.sh` (or `npm start`). Closing DXT-1 also stops its private
FastAPI service and conversion worker.

## Build a macOS application

Create an unpacked app for local testing:

```bash
npm run pack:mac
```

Create DMG and ZIP distribution files:

```bash
npm run dist:mac
```

Build output is written to `dist/`. A build made on Apple Silicon targets Apple
Silicon; build on an Intel Mac for an Intel-specific artifact. Producing and
testing a universal app also requires compatible Python/native dependencies for
both architectures.

The packaged app intentionally does not bundle the large Python/PyTorch
environment. On its first launch it creates a private environment under
`~/Library/Application Support/DXT-1/runtime`, then downloads Demucs, PyTorch,
ADTOF, and their dependencies. The destination Mac therefore needs Python 3.9+
and FFmpeg. With Homebrew these can be installed using:

```bash
brew install python ffmpeg
```

The first conversion may additionally download Demucs model weights. Runtime
data, temporary jobs, model caches, and logs live below
`~/Library/Application Support/DXT-1/`. Completed and failed jobs are retained
for 24 hours by default and then cleaned up.

## Signing and notarizing a public release

The build commands work for local testing, but an unsigned app downloaded by
another person will be stopped or warned about by macOS Gatekeeper. A polished
public release needs an Apple Developer Program membership, a Developer ID
Application certificate, hardened-runtime signing, and Apple notarization.
Electron Builder can use signing credentials supplied through its documented
environment variables; keep certificates and Apple credentials outside this
repository and in CI secrets. See the official
[Electron signing guide](https://www.electronjs.org/docs/latest/tutorial/code-signing)
and [Electron Builder macOS configuration](https://www.electron.build/mac/).

## Troubleshooting

- Startup and Python service logs:
  `~/Library/Application Support/DXT-1/logs/backend.log`
- If setup was interrupted, quit DXT-1, remove only its `runtime` directory,
  and reopen it to retry the installation.
- If the app reports that FFmpeg is missing, run `brew install ffmpeg`.
- The `DXT_PYTHON` and `DXT_FFMPEG` environment variables can point development
  or test launches at specific executables.
