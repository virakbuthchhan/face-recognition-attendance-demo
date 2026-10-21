"""Collect runtime wheel license files and official OpenCV model licenses."""
from importlib.metadata import distribution
from pathlib import Path
import shutil
from urllib.request import urlopen

root = Path(__file__).resolve().parents[1]
destination = root / 'dist/THIRD-PARTY-NOTICES'
destination.mkdir(parents=True, exist_ok=True)
for package in ('PySide6-Essentials', 'shiboken6', 'numpy', 'opencv-python-headless',
                'httpx', 'httpcore', 'anyio', 'certifi', 'idna', 'h11', 'typing_extensions'):
    dist = distribution(package)
    for entry in dist.files or []:
        name = str(entry).lower()
        if '.dist-info/' in name and any(word in name for word in ('license', 'copying', 'notice')):
            target = destination / package / Path(str(entry).split('.dist-info/', 1)[1])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(dist.locate_file(entry), target)
for folder in ('face_detection_yunet', 'face_recognition_sface'):
    with urlopen(f'https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/{folder}/LICENSE', timeout=60) as response:
        (destination / f'{folder}-LICENSE.txt').write_bytes(response.read())
(destination / 'SOURCES.txt').write_text(
    'Runtime packages: https://pypi.org/ (versions in ../build-dependencies.txt)\n'
    'Qt / PySide6: https://code.qt.io/pyside/pyside-setup.git/ and https://download.qt.io/\n'
    'OpenCV face models: https://github.com/opencv/opencv_zoo/tree/main/models\n'
    'Model binaries are unmodified and SHA-256 verified by scripts/download_models.py.\n', encoding='utf-8')
