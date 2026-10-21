import secrets
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit
import cv2
import httpx
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget
from backend.security import hash_password, verify_password
from kiosk.storage import Store, data_dir
from shared.vision import MODEL_VERSION, Vision, match
from kiosk.feedback import Sounds, UnknownAlert
from kiosk.ui import CameraView, STYLESHEET


def valid_url(value):
    p = urlsplit(value)
    return p.scheme == 'https' or (p.scheme == 'http' and p.hostname in ('localhost', '127.0.0.1'))


class Network(QThread):
    state = Signal(str)

    def __init__(self, config, database):
        super().__init__()
        self.config, self.database = config, database
        self.snapshot = ([], 0)
        self.revoked = False
        self.wake = threading.Event()

    def run(self):
        store = Store(self.database)
        cache = store.get('face_cache', {})
        if cache.get('model_version') == MODEL_VERSION:
            self.snapshot = (cache.get('employees', []), cache.get('synced_at', 0))
        next_sync = 0
        try:
            with httpx.Client(base_url=self.config['url'], headers={'Authorization': 'Bearer '+self.config['token']}, timeout=8, trust_env=False) as client:
                while not self.isInterruptionRequested():
                    try:
                        if time.time() >= next_sync:
                            r = client.get('/api/kiosk/faces')
                            if r.status_code in (401, 403):
                                self.revoked = True; self.snapshot = ([], 0)
                                store.put('face_cache', {}); self.state.emit('Device revoked — contact administrator'); return
                            r.raise_for_status()
                            faces = r.json()
                            if faces['model_version'] != MODEL_VERSION:
                                self.snapshot = ([], 0)
                                store.put('face_cache', {})
                                self.state.emit('Model mismatch — update kiosk'); return
                            faces['synced_at'] = time.time(); store.put('face_cache', faces)
                            self.snapshot = (faces['employees'], faces['synced_at'])
                            next_sync = time.time() + 60
                        for event_id, body in store.pending():
                            if self.isInterruptionRequested():
                                break
                            r = client.post('/api/kiosk/scans', json=body)
                            if r.status_code in (401, 403):
                                self.revoked = True; self.snapshot = ([], 0)
                                store.put('face_cache', {}); self.state.emit('Device revoked — contact administrator'); return
                            if 400 <= r.status_code < 500 and r.status_code != 429:
                                store.reject(event_id, f'HTTP {r.status_code}')
                            else:
                                r.raise_for_status(); store.sent(event_id)
                        total, rejected = store.counts()
                        self.state.emit(f'Connected · {total-rejected} pending · {rejected} need admin review')
                    except (httpx.HTTPError, ValueError, KeyError):
                        self.state.emit('Offline · scans saved locally · retrying')
                        # Avoid spinning while allowing a prompt shutdown.
                    for _ in range(30):
                        if self.isInterruptionRequested():
                            return
                        if self.wake.wait(0.1):
                            self.wake.clear()
                            break
        finally:
            store.connection.close()


class Scanner(QThread):
    frame = Signal(QImage)
    state = Signal(str, str, str)
    feedback = Signal(str)

    def __init__(self, config, network, database):
        super().__init__()
        self.config, self.network, self.database = config, network, database

    def run(self):
        store = Store(self.database)
        camera = None
        try:
            model_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'models'
            vision = Vision(model_root)
            camera = cv2.VideoCapture(int(self.config.get('camera', 0)))
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 960); camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
            if not camera.isOpened():
                raise RuntimeError('Cannot open camera. Check camera permission and camera index.')
            cooldown = store.get('cooldown', {})
            candidate, streak, overlay_until = None, 0, 0
            unknown_alert = UnknownAlert()
            last_state = None
            while not self.isInterruptionRequested():
                ok, frame = camera.read()
                if not ok:
                    raise RuntimeError('Camera disconnected; reopen the application.')
                frame = cv2.resize(frame, (960, 540))
                faces = vision.detect(frame)
                near = [f for f in faces if f[2] / frame.shape[1] >= 0.20 and f[3] / frame.shape[0] >= 0.25]
                people, synced_at = self.network.snapshot
                state = ('idle', 'Ready when you are', 'Step closer and look straight at the camera.')
                accepted = None
                unknown = False
                if len(near) > 1:
                    state = ('multiple', 'One person at a time', 'Please leave space for the person checking in.')
                elif len(near) == 1:
                    face = near[0]
                    x, y, w, h = map(int, face[:4])
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (130, 215, 90), 2)
                    if self.network.revoked:
                        state = ('error', 'Kiosk unavailable', 'This device needs administrator attention.')
                    elif time.time() - synced_at > 86400:
                        state = ('error', 'Please reconnect this kiosk', 'The saved employee list needs an update.')
                    elif not people:
                        state = ('idle', 'Waiting for your team', 'Register an employee’s face in the admin portal to begin.')
                    else:
                        state = ('checking', 'Checking your face…', 'Hold still for a moment. You’re almost there.')
                        accepted = match(vision.embedding(frame, face), people)
                        if not accepted:
                            unknown = True
                            state = ('unknown', 'Face not recognized', 'Look straight ahead, or ask an administrator to register your face.')
                alert = unknown_alert.update(unknown, bool(near), time.monotonic())
                if unknown and unknown_alert.since is not None and time.monotonic() - unknown_alert.since < unknown_alert.delay:
                    state = ('checking', 'Checking your face…', 'Hold still and make sure your face is well lit.')
                if alert and time.monotonic() >= overlay_until:
                    self.feedback.emit('unknown')
                person_id = accepted[1]['id'] if accepted else None
                streak = streak + 1 if person_id and person_id == candidate else (1 if person_id else 0)
                candidate = person_id
                if accepted and streak >= 3:
                    score, person = accepted
                    now = time.time()
                    if now - cooldown.get(person_id, 0) >= 30:
                        store.enqueue({'event_id': str(uuid.uuid4()), 'employee_id': person_id, 'captured_at': now,
                                       'confidence': min(1.0, score), 'model_version': MODEL_VERSION})
                        self.network.wake.set()
                        cooldown[person_id] = now
                        cooldown = {k: v for k, v in cooldown.items() if now-v < 86400}
                        store.put('cooldown', cooldown)
                        last_state = ('success', 'Welcome, '+person['name']+'!', 'Your attendance is saved. Have a great day.')
                        self.state.emit(*last_state)
                        self.feedback.emit('success')
                        overlay_until = time.monotonic() + 2
                    else:
                        state = ('success', 'Welcome, '+person['name']+'!', 'Your recent scan is already saved. You’re all set.')
                if time.monotonic() >= overlay_until and state != last_state:
                    self.state.emit(*state)
                    last_state = state
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self.frame.emit(QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888).copy())
                self.msleep(50)
        except Exception as error:
            self.state.emit('error', 'Scanner needs attention', str(error))
        finally:
            if camera is not None:
                camera.release()
            store.connection.close()


class Window(QMainWindow):
    def __init__(self, autostart=True):
        super().__init__()
        self.setWindowTitle('Attendance Kiosk'); self.resize(1000, 820)
        self.setMinimumSize(720, 680)
        self.database = data_dir() / 'kiosk.db'
        self.store = Store(self.database)
        self.scanner = self.network = None
        self.pin_failures, self.locked_until = 0, 0
        self.sounds = Sounds(self, enabled=self.store.get('config', {}).get('sound_enabled', True))
        root = QWidget(); layout = QVBoxLayout(root); self.setCentralWidget(root)
        layout.setContentsMargins(35, 27, 35, 23); layout.setSpacing(20)
        header = QHBoxLayout(); header.setSpacing(12)
        mark = QLabel('⌑'); mark.setObjectName('BrandIcon'); mark.setFixedSize(43,43); mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(mark)
        brand = QVBoxLayout(); brand.setSpacing(3)
        title = QLabel('Attendance'); title.setObjectName('Brand'); brand.addWidget(title)
        subtitle = QLabel('A FAMILIAR FACE. A GREAT START.'); subtitle.setObjectName('Eyebrow'); brand.addWidget(subtitle)
        header.addLayout(brand); header.addStretch()
        date_time = QVBoxLayout(); date_time.setSpacing(2)
        self.clock = QLabel(); self.clock.setObjectName('Clock'); self.clock.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.date = QLabel(); self.date.setObjectName('Date'); self.date.setAlignment(Qt.AlignmentFlag.AlignRight)
        date_time.addWidget(self.clock); date_time.addWidget(self.date); header.addLayout(date_time)
        layout.addLayout(header)
        intro = QVBoxLayout(); intro.setSpacing(5)
        welcome = QLabel('A seamless start to your day.'); welcome.setObjectName('Welcome'); intro.addWidget(welcome)
        subtitle = QLabel('Step up, look at the camera, and you’re on your way.'); subtitle.setObjectName('Subtitle'); intro.addWidget(subtitle)
        layout.addLayout(intro)
        self.video = CameraView(); layout.addWidget(self.video, 1)
        self.status_card = QWidget(); self.status_card.setObjectName('StatusCard')
        status_layout = QHBoxLayout(self.status_card); status_layout.setContentsMargins(23,20,23,20); status_layout.setSpacing(17)
        self.status_symbol = QLabel('⌑'); self.status_symbol.setObjectName('StatusSymbol'); self.status_symbol.setFixedSize(46,46); self.status_symbol.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self.status_symbol)
        status_copy = QVBoxLayout(); status_copy.setSpacing(5)
        self.status = QLabel(); self.status.setObjectName('StatusTitle'); self.status.setWordWrap(True)
        self.detail = QLabel(); self.detail.setObjectName('StatusDetail'); self.detail.setWordWrap(True)
        status_copy.addWidget(self.status); status_copy.addWidget(self.detail); status_layout.addLayout(status_copy,1)
        self.step_tag = QLabel('READY TO SCAN'); self.step_tag.setObjectName('StepTag'); status_layout.addWidget(self.step_tag)
        layout.addWidget(self.status_card)
        footer = QHBoxLayout(); footer.setSpacing(8)
        footer_copy = QVBoxLayout(); footer_copy.setSpacing(5)
        self.connection = QLabel('○  Waiting for connection'); self.connection.setObjectName('Connection'); footer_copy.addWidget(self.connection)
        privacy = QLabel('Video stays on this device. Only attendance events are sent.'); privacy.setObjectName('Privacy'); footer_copy.addWidget(privacy)
        footer.addLayout(footer_copy); footer.addStretch()
        self.audio_label = QLabel('SOUND ON' if self.sounds.enabled else 'SOUND OFF'); self.audio_label.setObjectName('Eyebrow'); footer.addWidget(self.audio_label)
        settings = QPushButton('⚙'); settings.setObjectName('Settings'); settings.setAccessibleName('Administrator settings'); settings.setFixedSize(34,34)
        settings.setToolTip('Administrator settings · PIN required'); settings.clicked.connect(self.settings); footer.addWidget(settings)
        layout.addLayout(footer)
        self.setStyleSheet(STYLESHEET)
        self.clock_timer = QTimer(self); self.clock_timer.timeout.connect(self.update_clock); self.clock_timer.start(1000); self.update_clock()
        self.present('idle', 'Ready when you are', 'Step closer and look straight at the camera.')
        if not self.store.get('config'):
            self.present('idle', 'Let’s get this kiosk ready', 'An administrator can connect this device using the settings button.')
        if autostart and self.store.get('config'):
            self.start()

    def update_clock(self):
        from datetime import datetime
        now = datetime.now().astimezone()
        self.clock.setText(now.strftime('%I:%M %p').lstrip('0'))
        self.date.setText(now.strftime('%A, %d %B'))

    def present(self, mode, title, detail):
        from kiosk.ui import COLORS
        color = COLORS.get(mode, COLORS['idle'])
        self.video.setMode(mode)
        self.status.setText(title); self.detail.setText(detail)
        self.status_symbol.setText({'success':'✓','unknown':'?','error':'!','multiple':'↔','checking':'⋯'}.get(mode,'⌑'))
        self.status_symbol.setStyleSheet(f'color:{color};')
        self.status.setStyleSheet(f'color:{color};')
        self.step_tag.setText({'success':'SCAN SAVED','unknown':'TRY AGAIN','error':'NEEDS ATTENTION',
                               'multiple':'MAKE SOME SPACE','checking':'CHECKING'}.get(mode,'READY TO SCAN'))

    def connection_state(self, text):
        self.connection.setText(('●  ' if text.startswith('Connected') else '○  ') + text)

    def start(self):
        config = self.store.get('config')
        self.network = Network(config, self.database); self.network.state.connect(self.connection_state)
        self.scanner = Scanner(config, self.network, self.database)
        self.scanner.frame.connect(self.video.setFrame)
        self.scanner.state.connect(self.present)
        self.scanner.feedback.connect(self.sounds.play)
        self.network.start(); self.scanner.start()

    def stop(self):
        self.sounds.stop()
        for worker in (self.scanner, self.network):
            if worker:
                worker.requestInterruption()
        for worker in (self.scanner, self.network):
            if worker:
                worker.wait()
        self.scanner = self.network = None

    def settings(self):
        if time.monotonic() < self.locked_until:
            QMessageBox.warning(self, 'Locked', 'Try again in one minute.'); return
        encoded = self.store.get('pin')
        pin, ok = QInputDialog.getText(self, 'Administrator settings', 'Admin PIN:' if encoded else 'Set a new admin PIN (6+ digits):', QLineEdit.EchoMode.Password)
        if not ok:
            return
        if encoded and not verify_password(pin, encoded):
            self.pin_failures += 1
            if self.pin_failures >= 5:
                self.locked_until = time.monotonic() + 60; self.pin_failures = 0
            QMessageBox.warning(self, 'Denied', 'Incorrect PIN'); return
        if not encoded:
            if len(pin) < 6 or not pin.isdigit():
                QMessageBox.warning(self, 'PIN', 'Use at least six digits.'); return
            confirm, ok = QInputDialog.getText(self, 'Confirm PIN', 'Repeat new PIN:', QLineEdit.EchoMode.Password)
            if not ok or not secrets.compare_digest(pin, confirm):
                return
            self.store.put('pin', hash_password(pin))
        self.pin_failures = 0
        config = self.store.get('config', {})
        dialog = QDialog(self); dialog.setWindowTitle('Kiosk configuration'); form = QFormLayout(dialog)
        url = QLineEdit(config.get('url', 'https://attendance.example.com'))
        token = QLineEdit(config.get('token', '')); token.setEchoMode(QLineEdit.EchoMode.Password)
        camera = QLineEdit(str(config.get('camera', 0)))
        form.addRow('Central API URL', url); form.addRow('Device token', token); form.addRow('Camera index', camera)
        sound_enabled = QCheckBox('Play success and unrecognized-face sounds'); sound_enabled.setChecked(config.get('sound_enabled', True))
        form.addRow('Audio feedback', sound_enabled)
        test_sound = QPushButton('Preview success sound')
        def preview_sound():
            old = self.sounds.enabled
            self.sounds.enabled = sound_enabled.isChecked(); self.sounds.play('success'); self.sounds.enabled = old
        test_sound.clicked.connect(preview_sound); form.addRow('', test_sound)
        total, rejected = self.store.counts(); form.addRow(QLabel(f'{total-rejected} pending scans; {rejected} rejected (inspect kiosk.db).'))
        save = QPushButton('Save and restart scanner'); save.setObjectName('Primary'); save.clicked.connect(dialog.accept); form.addRow(save)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not valid_url(url.text()) or not token.text().strip() or not camera.text().isdigit():
            QMessageBox.warning(self, 'Invalid configuration', 'Use an HTTPS API origin, a device token, and a numeric camera index. HTTP is allowed only on localhost.'); return
        # Pending events belong to the original deployment/device identity.
        if total and config and (url.text().rstrip('/') != config['url'] or token.text().strip() != config['token']):
            QMessageBox.warning(self, 'Pending scans', 'Drain or archive local scans before changing server or device identity.'); return
        self.stop()
        self.store.put('face_cache', {})
        self.store.put('config', {'url': url.text().rstrip('/'), 'token': token.text().strip(), 'camera': int(camera.text()), 'sound_enabled': sound_enabled.isChecked()})
        self.sounds.enabled = sound_enabled.isChecked()
        self.audio_label.setText('SOUND ON' if self.sounds.enabled else 'SOUND OFF')
        self.start()

    def closeEvent(self, event):
        self.stop(); self.store.connection.close(); event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Window(); window.show()
    sys.exit(app.exec())
