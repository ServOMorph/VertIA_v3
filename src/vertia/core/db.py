from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS preferences (
        cle TEXT PRIMARY KEY,
        valeur TEXT NOT NULL
    );
    """,
]


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.session() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            for index in range(version, len(MIGRATIONS)):
                conn.executescript(MIGRATIONS[index])
                conn.execute(f"PRAGMA user_version = {index + 1}")
            return conn.execute("PRAGMA user_version").fetchone()[0]

    def get_preference(self, key: str, default: str | None = None) -> str | None:
        with self.session() as conn:
            row = conn.execute("SELECT valeur FROM preferences WHERE cle = ?", (key,)).fetchone()
        return row["valeur"] if row else default

    def set_preference(self, key: str, value: str) -> None:
        with self.session() as conn:
            conn.execute(
                "INSERT INTO preferences (cle, valeur) VALUES (?, ?) "
                "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
                (key, value),
            )
