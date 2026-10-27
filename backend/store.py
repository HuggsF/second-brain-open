"""Local, bounded observation history and hashed authentication secrets."""
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS secrets(hash TEXT PRIMARY KEY,kind TEXT,expires REAL);
                CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY,environment TEXT,at REAL,payload TEXT,error TEXT);
                CREATE INDEX IF NOT EXISTS observation_target ON observations(environment,id);
            ''')

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def issue(self, kind, seconds):
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('DELETE FROM secrets WHERE expires < ?', (time.time(),))
            if kind == 'bootstrap':
                db.execute('DELETE FROM secrets WHERE kind=?', (kind,))
            db.execute('INSERT INTO secrets VALUES(?,?,?)', (digest(token), kind, time.time()+seconds))
        return token

    def authorize(self, token, kind, consume=False):
        with self.connect() as db:
            if consume:
                row = db.execute('DELETE FROM secrets WHERE hash=? AND kind=? AND expires>? RETURNING hash', (digest(token), kind, time.time())).fetchone()
            else:
                row = db.execute('SELECT hash FROM secrets WHERE hash=? AND kind=? AND expires>?', (digest(token), kind, time.time())).fetchone()
        return row is not None

    def record(self, environment, payload=None, error=None):
        with self.connect() as db:
            db.execute('INSERT INTO observations(environment,at,payload,error) VALUES(?,?,?,?)', (environment, time.time(), json.dumps(payload) if payload is not None else None, error))
            db.execute('DELETE FROM observations WHERE at<? OR id < (SELECT COALESCE(MAX(id),0)-10000 FROM observations)', (time.time()-7*86400,))

    def read(self, environment, limit=30):
        with self.connect() as db:
            rows = db.execute('SELECT id,at,payload,error FROM observations WHERE environment=? ORDER BY id DESC LIMIT ?', (environment,limit)).fetchall()
        return [dict(id=r[0], collected_at=r[1], report=json.loads(r[2]) if r[2] else None, error=r[3]) for r in rows]

    def latest(self, environment, max_age=180):
        attempts = self.read(environment, 1)
        with self.connect() as db:
            row = db.execute('SELECT id,at,payload FROM observations WHERE environment=? AND payload IS NOT NULL ORDER BY id DESC LIMIT 1', (environment,)).fetchone()
        age = max(0,time.time()-row[1]) if row else None
        return dict(environment=environment, last_attempt=attempts[0] if attempts else None,
                    observation=dict(id=row[0],collected_at=row[1],report=json.loads(row[2])) if row else None,
                    age_seconds=age, stale=age is None or age>max_age,
                    collection_failed=bool(attempts and attempts[0]['error']))
