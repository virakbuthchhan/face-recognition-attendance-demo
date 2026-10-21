"""Quiet, asynchronous audio feedback; uses platform players without extra GUI modules."""
import shutil
import sys
from pathlib import Path
from PySide6.QtCore import QObject, QProcess
from PySide6.QtWidgets import QApplication


class UnknownAlert:
    """Alert once for a sustained unknown face; re-arm only after the area clears."""
    def __init__(self, delay=1.5, clear_after=2.0):
        self.delay, self.clear_after = delay, clear_after
        self.since = self.absent_since = None
        self.alerted = False

    def update(self, unknown, present, now):
        if not present:
            self.since = None
            if self.absent_since is None:
                self.absent_since = now
            if now - self.absent_since >= self.clear_after:
                self.alerted = False
            return False
        self.absent_since = None
        if not unknown:
            self.since = None
            return False
        if self.since is None:
            self.since = now
        if not self.alerted and now - self.since >= self.delay:
            self.alerted = True
            return True
        return False


class Sounds(QObject):
    def __init__(self, parent=None, enabled=True):
        super().__init__(parent)
        self.enabled = enabled
        self.player = QProcess(self)
        self.root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'kiosk/assets'

    def play(self, kind):
        if not self.enabled or kind not in ('success', 'unknown'):
            return
        path = self.root / f'{kind}.wav'
        if not path.exists():
            QApplication.beep()
            return
        if sys.platform == 'win32':
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            return
        player = '/usr/bin/afplay' if sys.platform == 'darwin' else shutil.which('paplay') or shutil.which('aplay')
        if player:
            self.stop()
            self.player.start(player, [str(path)])
        else:
            QApplication.beep()

    def stop(self):
        if self.player.state() != QProcess.ProcessState.NotRunning:
            self.player.kill()
            self.player.waitForFinished(1000)
        if sys.platform == 'win32':
            import winsound
            winsound.PlaySound(None, 0)
