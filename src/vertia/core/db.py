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
    """
    CREATE TABLE dossiers (
        id TEXT PRIMARY KEY, nom TEXT NOT NULL, system_prompt TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE conversations (
        id TEXT PRIMARY KEY, dossier_id TEXT REFERENCES dossiers(id) ON DELETE SET NULL,
        titre TEXT NOT NULL, modele TEXT NOT NULL,
        resume TEXT NOT NULL DEFAULT '', resume_count INTEGER NOT NULL DEFAULT 0,
        date_maj TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
        contenu TEXT NOT NULL, statut TEXT NOT NULL,
        erreur TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX messages_conversation ON messages(conversation_id, id);
    """,
    """
    CREATE TABLE jobs (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, engine TEXT NOT NULL,
        payload TEXT NOT NULL DEFAULT '{}', priority INTEGER NOT NULL DEFAULT 0,
        resumable INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'attente', progress REAL NOT NULL DEFAULT 0,
        error TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 0,
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX jobs_pending ON jobs(status, priority);
    """,
    """
    CREATE TABLE actions (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        message_id INTEGER NOT NULL, tool TEXT NOT NULL, parameters TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'proposee', job_id TEXT,
        result TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX actions_conversation ON actions(conversation_id);
    """,
    """
    CREATE TABLE fichiers (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        action_id TEXT NOT NULL, job_id TEXT NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('image','audio','video')),
        mime TEXT NOT NULL, name TEXT NOT NULL, size INTEGER NOT NULL,
        prompt TEXT NOT NULL, parameters TEXT NOT NULL,
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX fichiers_conversation ON fichiers(conversation_id);
    """,
    """
    ALTER TABLE dossiers ADD COLUMN epingle INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE dossiers ADD COLUMN position INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE conversations ADD COLUMN epingle INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE conversations ADD COLUMN position INTEGER NOT NULL DEFAULT 0;
    """,
    """
    CREATE TABLE demandes (
        id TEXT PRIMARY KEY, session TEXT NOT NULL, capacite TEXT NOT NULL,
        params TEXT NOT NULL, critere TEXT NOT NULL DEFAULT '', essais_max INTEGER NOT NULL,
        etat TEXT NOT NULL DEFAULT 'attente', analyse_requise INTEGER NOT NULL DEFAULT 0,
        motif_code TEXT NOT NULL DEFAULT '', erreur TEXT NOT NULL DEFAULT '',
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX demandes_session ON demandes(session, capacite);
    CREATE TABLE essais (
        demande_id TEXT NOT NULL REFERENCES demandes(id), numero INTEGER NOT NULL,
        job_id TEXT, etat TEXT NOT NULL DEFAULT 'attente', params TEXT NOT NULL,
        motif TEXT NOT NULL DEFAULT '', chemins TEXT NOT NULL DEFAULT '[]',
        module TEXT NOT NULL, version TEXT NOT NULL, duree REAL NOT NULL DEFAULT 0,
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(demande_id, numero)
    );
    CREATE TABLE retours (
        id INTEGER PRIMARY KEY AUTOINCREMENT, demande_id TEXT NOT NULL,
        numero INTEGER NOT NULL, verdict TEXT NOT NULL, motif TEXT NOT NULL DEFAULT '',
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(demande_id, numero) REFERENCES essais(demande_id, numero)
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
