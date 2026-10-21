# Build a native AttendanceKiosk.app

Build on macOS for macOS; build on Windows for Windows. PyInstaller does not cross-compile an app bundle. Use Python 3.12 on macOS 14 or later with the same architecture as the target Mac (Apple Silicon arm64 or Intel x86_64). Produce/test separate builds for both architectures unless every dependency supports a universal build. Older macOS releases require selecting compatible Qt/OpenCV/NumPy wheels and lowering the bundle minimum after testing.

## 1. Prepare dependencies

From the repository root:

```sh
python3.12 -m venv .venv-kiosk
source .venv-kiosk/bin/activate
python -m pip install --upgrade pip
python -m pip install -r kiosk/requirements.txt
python scripts/download_models.py
python -m kiosk.app
```

Confirm enrollment and scanning against the running central service. Models are used by both central enrollment and the kiosk. The scanner itself does not depend on a running Python backend on the kiosk machine.

## 2. Build the app

```sh
python -m PyInstaller --clean --noconfirm kiosk/AttendanceKiosk.spec
open dist/AttendanceKiosk.app
```

The spec builds an onedir bundle with models and a camera usage description in `Info.plist`. It deliberately does not embed device credentials, a settings PIN, a face cache, or an administrator password. PyInstaller applies ad-hoc signing for local development when a distribution identity is absent.

Allow camera access when prompted. If denied, enable **System Settings → Privacy & Security → Camera → AttendanceKiosk**, then relaunch. If macOS does not show a prompt while running from the terminal, test the bundled app directly through Finder. Confirm the camera privacy prompt on each supported macOS version.

The first operator sets a settings PIN and provisions the server URL/device token using **⚙**. Subsequent launches open straight into the scanner. Copy the app to `/Applications` after testing. Keep application data in Application Support, never inside the signed app bundle.

## 3. Sign for distribution

Install your Apple Developer ID Application certificate in Keychain. Set your real bundle identifier in `kiosk/AttendanceKiosk.spec` before building a release. Build with your identity:

```sh
export CODESIGN_IDENTITY='Developer ID Application: Your Organization (TEAMID)'
python -m PyInstaller --clean --noconfirm kiosk/AttendanceKiosk.spec
codesign --verify --deep --strict --verbose=2 dist/AttendanceKiosk.app
```

The included entitlements request camera access. Test all native OpenCV/Qt libraries with the hardened runtime. Add other entitlements only if a verified native dependency needs them.

## 4. Notarize and staple

Create a Keychain notarization profile using Apple's supported `notarytool store-credentials` flow for your developer account. Do not place signing credentials in repository files. Then:

```sh
ditto -c -k --keepParent dist/AttendanceKiosk.app dist/AttendanceKiosk.zip
xcrun notarytool submit dist/AttendanceKiosk.zip --keychain-profile attendance-notary --wait
xcrun stapler staple dist/AttendanceKiosk.app
spctl --assess --type execute --verbose=2 dist/AttendanceKiosk.app
```

If notarization fails, inspect the notarization log and resolve it before distribution. Re-create the distributable archive **after stapling**:

```sh
ditto -c -k --keepParent dist/AttendanceKiosk.app dist/AttendanceKiosk-notarized.zip
```

Verify on a clean Mac: launch, camera consent, first provisioning, repeated recognition, unknown/ambiguous people, two near people, background people, server offline/reconnect, credential revocation, settings lockout, quit/relaunch with pending scans, and signed webhook receipt. First setup must happen before exposing the kiosk to attendees.

## Windows

On a Windows machine with Python 3.12:

```powershell
py -3.12 -m venv .venv-kiosk
.venv-kiosk\Scripts\Activate.ps1
python -m pip install -r kiosk/requirements.txt
python scripts/download_models.py
python -m PyInstaller --clean --noconfirm kiosk/AttendanceKiosk.spec
```

The Windows spec produces a single `dist/AttendanceKiosk.exe`, with Python, Qt, OpenCV, both face models and sound assets included. Send it with `docs/windows-readme.txt` and third-party notices. Run `python scripts/collect_notices.py` before packaging a distribution to collect the notices under `dist/THIRD-PARTY-NOTICES`. Allow camera access in Windows privacy settings, restrict the kiosk data directory ACL, and sign the executable/installer with your organization's signing certificate. The same device provisioning and scan flow applies.

The **Build Windows kiosk** GitHub Actions workflow builds on a Windows x64 runner and uploads the executable, setup notes, licenses, SHA-256 checksum, dependency versions and a packaged GUI smoke-test report. It runs on relevant pushes to main or can be started manually from Actions. The smoke test uses a temporary database and no camera or network; actual webcam matching and audio output require testing on the recipient's computer. The hosted artifact expires after 30 days, so download it for sharing. A remote kiosk needs a reachable HTTPS backend URL; your Mac's localhost URL cannot be used from your friend's PC.

[PyInstaller official build/signing options](https://www.pyinstaller.org/en/stable/usage.html)
