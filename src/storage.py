"""Optional SQLite snapshot history and latest-success retrieval."""
import sqlite3
from contextlib import closing
from datetime import datetime

from .data_adapter import Envelope


def connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5)
    try:
        with connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS snapshots (
                source TEXT, days INTEGER, synced_at TEXT, payload TEXT,
                PRIMARY KEY (source, days, synced_at)
            )""")
    except sqlite3.Error:
        connection.close()
        raise
    return connection


def save_snapshot(path: str, source: str, days: int, synced_at: datetime, payload: Envelope) -> None:
    with closing(connect(path)) as connection, connection:
        connection.execute("INSERT OR IGNORE INTO snapshots VALUES (?, ?, ?, ?)",
                           (source, days, synced_at.isoformat(), payload.model_dump_json()))


def latest_snapshot(path: str, source: str, days: int) -> tuple[Envelope, datetime] | None:
    with closing(connect(path)) as connection:
        row = connection.execute(
            "SELECT synced_at, payload FROM snapshots WHERE source = ? AND days = ? "
            "ORDER BY synced_at DESC LIMIT 1", (source, days)
        ).fetchone()
    if row:
        return Envelope.model_validate_json(row[1]), datetime.fromisoformat(row[0])
    return None
