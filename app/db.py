from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = Path(__file__).resolve().parent / "schema.sql"


def db_path() -> Path:
    raw = os.environ.get("SAFESYNC_DB", "./safesync.db")
    p = Path(raw)
    if not p.is_absolute():
        p = ROOT / p
    return p


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    own = conn is None
    conn = conn or connect()
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    if own:
        conn.commit()
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def rows_to_dicts(rows) -> list[dict]:
    return [row_to_dict(r) for r in rows]


def audit(conn: sqlite3.Connection, actor: str, action: str, entity: str, entity_id: str, detail: str = "") -> None:
    conn.execute(
        "INSERT INTO audit_log (actor, action, entity, entity_id, detail) VALUES (?,?,?,?,?)",
        (actor, action, entity, entity_id, detail),
    )
