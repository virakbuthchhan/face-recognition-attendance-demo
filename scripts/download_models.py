"""Download official OpenCV Zoo models; review model licenses before distribution."""
import hashlib
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1] / 'models'
ROOT.mkdir(exist_ok=True)
for folder, name, expected in [
    ('face_detection_yunet', 'face_detection_yunet_2023mar.onnx', '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4'),
    ('face_recognition_sface', 'face_recognition_sface_2021dec.onnx', '0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79'),
]:
    url = f'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/{folder}/{name}'
    destination = ROOT / name
    temporary = destination.with_suffix('.download')
    digest = hashlib.sha256()
    try:
        with urlopen(url, timeout=120) as response, temporary.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk); digest.update(chunk)
        if digest.hexdigest() != expected:
            raise RuntimeError('Model SHA-256 mismatch; review upstream changes before updating the approved hash')
        temporary.replace(destination)
        print(name, digest.hexdigest())
    finally:
        temporary.unlink(missing_ok=True)
