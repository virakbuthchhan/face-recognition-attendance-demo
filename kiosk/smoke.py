"""Exercise a packaged GUI without a webcam, credentials, network or personal data."""
import json
import platform
import sys
import tempfile
import traceback
import wave
from pathlib import Path


def run(window_class, report_path):
    report_path = Path(report_path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {'platform': platform.platform(), 'architecture': platform.machine(),
              'frozen': bool(getattr(sys, 'frozen', False)), 'camera_accessed': False}
    window = None
    try:
        import numpy as np
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from shared.vision import MODEL_VERSION, Vision
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
        vision = Vision(root / 'models')
        assert len(vision.detect(np.zeros((540, 960, 3), dtype=np.uint8))) == 0
        report['models'] = MODEL_VERSION
        for name in ('success', 'unknown'):
            with wave.open(str(root / 'kiosk/assets' / f'{name}.wav')) as audio:
                assert audio.getnframes() > 0
        report['sound_assets'] = 'success, unknown'
        app = QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            window = window_class(autostart=False, database=Path(directory) / 'kiosk.db')
            window.show()
            window.present('success', 'Welcome, Alex!', 'Your attendance is saved. Have a great day.')
            app.processEvents()
            assert window.grab().save(str(report_path.with_suffix('.png')))
            QTimer.singleShot(400, app.quit)
            app.exec()
            window.close()
            window = None
        report['gui'] = 'passed'
        report['ok'] = True
        return 0
    except Exception:
        if window is not None:
            window.close()
        report['ok'] = False
        report['error'] = traceback.format_exc()
        return 1
    finally:
        report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
