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

These are developer requirements for running from source. People installing a
release DMG do not need Node.js, Homebrew, Python, FFmpeg, or Terminal.

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

Before Electron Builder runs, `npm run prepare:runtime` downloads a
redistributable, architecture-specific CPython build and installs PyTorch,
Demucs, ADTOF-PyTorch, and the other backend packages into it. It also extracts
the architecture-specific FFmpeg executable supplied by `imageio-ffmpeg`.
Electron Builder places that complete runtime inside `DXT-1.app`.

```bash
npm run prepare:runtime
```

The runtime build is cached under `build/runtime-arm64` or
`build/runtime-x64`, so later builds do not reinstall it unless its inputs
change. The release artifact will be substantially larger because it contains
Python, PyTorch, and FFmpeg. The build process needs internet access, but the
end user's Mac does not need those tools installed.

Demucs may automatically download the selected model weights the first time a
particular model is used. This happens inside the app without Terminal or
administrator access. Application data, model caches, temporary jobs, and logs
live below `~/Library/Application Support/DXT-1/`. Completed and failed jobs
are retained for 24 hours by default and then cleaned up.

> **Distribution licensing warning:** a self-contained DMG redistributes its
> embedded dependencies. ADTOF-PyTorch currently publishes no license even
> though it contains code and converted ADTOF weights. Obtain permission or a
> licensing clarification from the relevant rights holders before publicly
> distributing the bundled application. Review `THIRD_PARTY_NOTICES.md` and
> preserve all notices and source/code obligations for the exact release.

## Signing and notarizing a public release

These instructions cover direct distribution from GitHub or a website using a
DMG. They do not cover submission to the Mac App Store, which uses different
certificates and sandboxing requirements.

A public macOS release needs all three of the following:

1. A **Developer ID Application** signature, proving who built the app.
2. Apple notarization, which scans the signed app and issues a ticket.
3. Stapling, which attaches that ticket so Gatekeeper can validate the app even
   when the user's Mac is offline.

An Apple Developer Program membership is required. DXT-1 already enables the
hardened runtime and uses the bundle ID `blog.topherpedersen.dxt1`.

### 1. Install the Apple development tools

Install the latest stable Xcode from the Mac App Store, launch it once, accept
its license, and install any requested components. Confirm that its command-line
tools are selected under **Xcode > Settings > Locations**. You can also check
from Terminal:

```bash
xcode-select -p
xcrun notarytool --version
```

### 2. Create a Developer ID Application certificate

In Xcode, open **Xcode > Settings > Accounts**, add the Apple ID belonging to
the paid developer account, select the correct team, and click **Manage
Certificates**. Click the plus button and create a **Developer ID Application**
certificate.

This certificate is for apps distributed outside the Mac App Store. Do not use
an Apple Development, Apple Distribution, or Mac App Distribution certificate.
A Developer ID Installer certificate is only needed for a PKG installer; DXT-1
currently distributes a DMG and ZIP.

Verify that the signing identity and its private key are available in the login
keychain:

```bash
security find-identity -v -p codesigning
```

The output should contain an identity similar to:

```text
Developer ID Application: Your Name (ABCDE12345)
```

`ABCDE12345` is the Apple Developer Team ID. It is also shown under Membership
Details in the Apple Developer account.

### 3. Make release builds fail if signing or notarization is missing

Before publishing a release, update the `build` section of `package.json` to
include `forceCodeSigning`, and add `notarize` under `mac`:

```json
"build": {
  "forceCodeSigning": true,
  "mac": {
    "category": "public.app-category.music",
    "hardenedRuntime": true,
    "notarize": true,
    "gatekeeperAssess": false,
    "minimumSystemVersion": "12.0",
    "target": ["dmg", "zip"]
  }
}
```

Keep all the other existing `build` settings. `forceCodeSigning` prevents
Electron Builder from silently producing an unsigned release if the certificate
cannot be found. `notarize` makes Electron Builder submit the signed app to
Apple and staple the successful notarization ticket.

### 4. Create notarization credentials

The simplest option for a release built on this Mac is an app-specific password:

1. Sign in at [account.apple.com](https://account.apple.com/).
2. Open **Sign-In and Security > App-Specific Passwords**.
3. Create a password named `DXT-1 Notarization` and save it in a password
   manager. This is not the normal Apple Account password.

Electron Builder needs the Apple Account email, app-specific password, and Team
ID. Set them only in the Terminal session used for the release build:

```bash
export APPLE_ID="your-apple-account@example.com"
export APPLE_TEAM_ID="ABCDE12345"
read -s APPLE_APP_SPECIFIC_PASSWORD
export APPLE_APP_SPECIFIC_PASSWORD
```

Paste the app-specific password at the silent prompt and press Return. Using
`read -s` keeps it out of shell history. Never add this password, a `.p12`
certificate, or any signing secret to the repository.

For automated CI builds, prefer an App Store Connect API key stored in the CI
service's encrypted secrets. Electron Builder supports `APPLE_API_KEY`,
`APPLE_API_KEY_ID`, and `APPLE_API_ISSUER`; see its notarization documentation
linked below.

### 5. Build the signed and notarized release

With the Developer ID certificate in Keychain and the three notarization
variables set, run from the repository root:

```bash
rm -rf dist
npm ci
npm run dist:mac
```

Electron Builder should report that it found the Developer ID Application
identity, signed the app, submitted it for notarization, and completed stapling.
Notarization can take several minutes. A failure is not safe to ignore; do not
publish artifacts until every verification below passes.

After the build, clear the password from the current shell:

```bash
unset APPLE_APP_SPECIFIC_PASSWORD
```

The DMG and ZIP are written to `dist/`. Build on Apple Silicon for an arm64
release and on an Intel Mac for an x64 release. If both are distributed, label
the downloads clearly. A universal Electron bundle does not by itself make all
Python and native conversion dependencies universal.

### 6. Verify the release before uploading it

First locate the generated application and DMG:

```bash
find dist -maxdepth 3 -name "DXT-1.app" -print
find dist -maxdepth 1 -name "*.dmg" -print
```

Substitute the printed paths in these commands:

```bash
codesign --verify --deep --strict --verbose=2 "dist/mac-arm64/DXT-1.app"
codesign -dv --verbose=4 "dist/mac-arm64/DXT-1.app"
xcrun stapler validate "dist/mac-arm64/DXT-1.app"
spctl --assess --type exec --verbose=4 "dist/mac-arm64/DXT-1.app"
spctl --assess --type open --context context:primary-signature --verbose=4 "dist/DXT-1-0.5.0-arm64.dmg"
```

The exact directory and filename include the version and architecture and may
differ. The important results are a valid code signature, a valid stapled
ticket, and Gatekeeper reporting `accepted` with a notarized Developer ID
source.

As a final real-world test, copy the DMG to a different Mac that does not have
the development certificate, open it, drag DXT-1 to Applications, and launch
it. The user should receive the normal first-launch confirmation identifying
the developer, not an unidentified-developer or damaged-app warning.

### 7. Distribute the DMG

Upload the notarized DMG to a GitHub Release or a website served over HTTPS.
Publish its architecture, minimum supported macOS version, version number, and
SHA-256 checksum. Generate the checksum with:

```bash
shasum -a 256 "dist/DXT-1-0.5.0-arm64.dmg"
```

Users download the DMG, open it, drag DXT-1 into Applications, and launch it.
The DMG contains the application runtime. Users do not need Homebrew, Python,
FFmpeg, Node.js, npm, or command-line setup. They only open the DMG, drag DXT-1
to Applications, and launch it. An internet connection may be used
automatically when a Demucs model is selected for the first time.

Official references:

- [Electron code-signing overview](https://www.electronjs.org/docs/latest/tutorial/code-signing)
- [Electron Builder macOS signing](https://www.electron.build/docs/features/code-signing/code-signing-mac/)
- [Electron Builder notarization](https://www.electron.build/docs/notarization/)
- [Apple notarization troubleshooting](https://developer.apple.com/documentation/security/resolving-common-notarization-issues)

## Troubleshooting

- Startup and Python service logs:
  `~/Library/Application Support/DXT-1/logs/backend.log`
- If a packaged build reports that Python or FFmpeg is missing, it was built
  without `npm run prepare:runtime`; rebuild and reinstall the complete DMG.
- The `DXT_PYTHON` and `DXT_FFMPEG` environment variables can point development
  or test launches at specific executables.
