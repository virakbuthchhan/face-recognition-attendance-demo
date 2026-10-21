import wave
from pathlib import Path
from kiosk.feedback import UnknownAlert


def test_unknown_needs_sustained_presence():
    gate = UnknownAlert()
    assert not gate.update(True, True, 0)
    assert not gate.update(True, True, 1.49)
    assert gate.update(True, True, 1.5)
    assert not gate.update(True, True, 60)


def test_empty_camera_is_silent_and_brief_detection_does_not_alert():
    gate = UnknownAlert()
    assert not gate.update(False, False, 0)
    assert not gate.update(False, False, 100)
    assert not gate.update(True, True, 101)
    assert not gate.update(False, True, 102)
    assert not gate.update(True, True, 103)
    assert not gate.update(True, True, 104)


def test_unknown_rearms_only_when_area_clears_for_two_seconds():
    gate = UnknownAlert()
    gate.update(True, True, 0)
    assert gate.update(True, True, 2)
    gate.update(False, False, 3)
    assert not gate.update(True, True, 4)
    assert not gate.update(True, True, 6)
    gate.update(False, False, 7)
    gate.update(False, False, 9)
    assert not gate.update(True, True, 10)
    assert gate.update(True, True, 12)


def test_sound_assets_are_distinct_playable_pcm():
    root = Path(__file__).resolve().parents[1] / 'kiosk/assets'
    contents = []
    for kind in ('success', 'unknown'):
        with wave.open(str(root / f'{kind}.wav')) as audio:
            assert audio.getnchannels() == 1
            assert audio.getsampwidth() == 2
            assert audio.getframerate() == 44100
            assert .3 < audio.getnframes()/44100 < .6
            contents.append(audio.readframes(audio.getnframes()))
    assert contents[0] != contents[1]


def test_success_chime_follows_durable_save_and_respects_cooldown(tmp_path, monkeypatch):
    import threading
    import time
    import uuid
    from types import SimpleNamespace
    import numpy as np
    import kiosk.app as kiosk
    from kiosk.storage import Store
    person = {'id': str(uuid.uuid4()), 'name': 'Test Person'}
    class Camera:
        reads = 0
        released = False
        def set(self, *args): pass
        def isOpened(self): return True
        def read(self):
            self.reads += 1
            return True, np.zeros((540, 960, 3), dtype=np.uint8)
        def release(self): self.released = True
    camera = Camera()
    class Vision:
        def __init__(self, *args): pass
        def detect(self, image): return [np.array([200, 100, 250, 250] + [0] * 11)]
        def embedding(self, *args): return [1]
    class Scanner(kiosk.Scanner):
        def isInterruptionRequested(self): return camera.reads >= 6
        def msleep(self, *args): pass
    monkeypatch.setattr(kiosk, 'Vision', Vision)
    monkeypatch.setattr(kiosk.cv2, 'VideoCapture', lambda *args: camera)
    monkeypatch.setattr(kiosk, 'match', lambda *args: (.8, person))
    database = tmp_path / 'kiosk.db'
    network = SimpleNamespace(snapshot=([person], time.time()), revoked=False, wake=threading.Event())
    scanner = Scanner({}, network, database)
    feedback = []
    def on_feedback(kind):
        with Store(database).connection as connection:
            # The UI never announces success before the scan exists on disk.
            assert connection.execute('SELECT COUNT(*) FROM scans').fetchone()[0] == 1
        feedback.append(kind)
    scanner.feedback.connect(on_feedback)
    scanner.run()
    assert feedback == ['success']
    assert network.wake.is_set()
    assert camera.released
