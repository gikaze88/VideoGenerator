"""
Configuration SQLite avec SQLModel.
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from backend.config import DATABASE_PATH

CREATE_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    style TEXT NOT NULL,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    output_video_path TEXT,
    output_dir TEXT,
    log_file TEXT,
    error_message TEXT,
    youtube_video_id TEXT,
    youtube_status TEXT
)
"""


def get_connection():
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_db(conn):
    """Ajoute les colonnes manquantes à la table jobs (migrations incrémentales)."""
    cursor = conn.execute("PRAGMA table_info(jobs)")
    existing = {row[1] for row in cursor.fetchall()}
    new_columns = {
        "youtube_video_id": "TEXT",
        "youtube_status": "TEXT",
    }
    for col, col_type in new_columns.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {col_type}")


def init_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute(CREATE_JOBS_TABLE)
        _migrate_db(conn)
        conn.commit()


def row_to_dict(row) -> dict:
    return dict(row) if row else None
