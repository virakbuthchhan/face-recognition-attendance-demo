ATTENDANCE KIOSK - WINDOWS x64 DEMO

Run AttendanceKiosk.exe on a Windows 10/11 x64 computer. Python is not required.
The first start can take a little longer while the bundled files unpack.

FIRST SETUP
1. Open the settings gear and set your administrator PIN (six or more digits).
2. Enter the HTTPS central backend URL supplied by your administrator.
3. Enter a unique device token created under Kiosks in the admin portal.
4. Leave camera index at 0 for the built-in webcam, then save.
5. Allow desktop app camera access in Windows Settings > Privacy & security > Camera.
6. Register employee faces in the central admin portal, then allow the kiosk to sync.

The URL 127.0.0.1 refers to the computer running this app. It will not connect to
your friend's Mac. A remote backend must be reachable over HTTPS. Device tokens,
employee data, administrator passwords and PINs are not included in this build.

Successful scans are saved locally before upload. Success and unknown-face sounds
use the Windows system volume. Empty camera frames do not trigger error sounds.
Settings, cached faces and pending scans are stored under:
%LOCALAPPDATA%\AttendanceKiosk\kiosk.db

This is an unsigned demo build, not a code-signed production installer. The build
checks GUI startup, face-model loading and sound assets without using a camera.
Real webcam recognition and audio output still need testing on your computer.
Third-party model and runtime license notices accompany the download.
