import json
import os
import sqlite3
import sys
from pathlib import Path


def data_dir():
    if sys.platform == 'darwin':
        root = Path.home() / 'Library/Application Support/AttendanceKiosk'
    elif sys.platform == 'win32':
        root = Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'AttendanceKiosk'
    else:
        root = Path.home() / '.local/share/attendance-kiosk'
    root.mkdir(parents=True, exist_ok=True)
    if sys.platform != 'win32':
        root.chmod(0o700)
    return root


class Store:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        self.connection.execute('CREATE TABLE IF NOT EXISTS scans (id TEXT PRIMARY KEY, body TEXT NOT NULL, error TEXT)')
        self.connection.commit()
        if sys.platform != 'win32':
            Path(path).chmod(0o600)

    def get(self, key, default=None):
        row = self.connection.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        self.connection.execute('INSERT OR REPLACE INTO settings VALUES (?, ?)', (key, json.dumps(value)))
        self.connection.commit()

    def enqueue(self, body):
        self.connection.execute('INSERT OR IGNORE INTO scans VALUES (?, ?, NULL)', (body['event_id'], json.dumps(body)))
        self.connection.commit()

    def pending(self):
        return [(row[0], json.loads(row[1])) for row in self.connection.execute('SELECT id, body FROM scans WHERE error IS NULL ORDER BY rowid LIMIT 50')]

    def sent(self, event_id):
        self.connection.execute('DELETE FROM scans WHERE id=?', (event_id,)); self.connection.commit()

    def reject(self, event_id, error):
        self.connection.execute('UPDATE scans SET error=? WHERE id=?', (error, event_id)); self.connection.commit()

    def counts(self):
        return self.connection.execute('SELECT COUNT(*), COUNT(error) FROM scans').fetchone()
