"""Connections and atomic, versioned schema initialization."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DATABASE = Path(__file__).resolve().parents[3] / 'data' / 'customer_support.sqlite3'
APPLICATION_ID = 1129533520


@contextmanager
def connection(path=DEFAULT_DATABASE, *, readonly=False):
    path = Path(path).resolve()
    db = sqlite3.connect(path.as_uri() + ('?mode=ro' if readonly else '?mode=rw'), uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    try:
        yield db
    finally:
        db.close()


def initialize(path=DEFAULT_DATABASE):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids replacing existing files, including unrelated databases.
    try:
        with path.open('xb'):
            pass
    except FileExistsError:
        pass
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            app_id = db.execute('PRAGMA application_id').fetchone()[0]
            version = db.execute('PRAGMA user_version').fetchone()[0]
            objects = db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if app_id != APPLICATION_ID and (app_id != 0 or version != 0 or objects):
                raise ValueError('Refusing to modify an unrelated database')
            if version > 2:
                raise ValueError('Database schema is newer than this application')
            if version == 0:
                # Execute statements separately; executescript would implicitly commit.
                for statement in Path(__file__).with_name('schema.sql').read_text(encoding='utf-8').split(';'):
                    if statement.strip():
                        db.execute(statement)
                db.execute(f'PRAGMA application_id = {APPLICATION_ID}')
                db.execute('PRAGMA user_version = 1')
            if version < 2:
                for statement in Path(__file__).with_name('agent_schema.sql').read_text(encoding='utf-8').split(';'):
                    if statement.strip():
                        db.execute(statement)
                db.execute('PRAGMA user_version = 2')
            db.commit()
        except Exception:
            db.rollback()
            raise
