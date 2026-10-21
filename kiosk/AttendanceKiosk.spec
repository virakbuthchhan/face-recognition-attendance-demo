from pathlib import Path
import os
import sys

root = Path(SPECPATH).parent
models = root / 'models'
required = ['face_detection_yunet_2023mar.onnx', 'face_recognition_sface_2021dec.onnx']
for filename in required:
    if not (models / filename).is_file():
        raise SystemExit('Missing model: run python scripts/download_models.py first')
a = Analysis([str(root / 'kiosk/app.py')], pathex=[str(root)],
             binaries=[], datas=[(str(models / f), 'models') for f in required] + [(str(root / 'kiosk/assets'), 'kiosk/assets')],
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['PyQt5', 'PyQt6', 'tkinter'], noarchive=False)
pyz = PYZ(a.pure)
if sys.platform == 'win32':
    # Onefile includes Python, Qt, OpenCV, both models and sound assets.
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='AttendanceKiosk',
              debug=False, strip=False, upx=False, console=False)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='AttendanceKiosk',
              debug=False, strip=False, upx=False, console=False,
              codesign_identity=os.getenv('CODESIGN_IDENTITY') or None,
              entitlements_file=str(root / 'kiosk/entitlements.plist') if sys.platform == 'darwin' else None)
    collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='AttendanceKiosk')
    if sys.platform == 'darwin':
        app = BUNDLE(collection, name='AttendanceKiosk.app', bundle_identifier='com.example.attendancekiosk',
                     info_plist={'NSCameraUsageDescription': 'Scan registered employees to record attendance.',
                                 'NSHighResolutionCapable': True, 'LSMinimumSystemVersion': '14.0'})
