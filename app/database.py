"""Conexión y esquema de la base de datos SQLite donde se guarda el progreso."""

import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "progreso.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS progress (
    question_id   TEXT PRIMARY KEY,
    status        TEXT NOT NULL,           -- aprendiendo | en_repaso | dominada
    streak        INTEGER NOT NULL DEFAULT 0,  -- aciertos consecutivos
    interval_days INTEGER NOT NULL DEFAULT 0,
    times_seen    INTEGER NOT NULL DEFAULT 0,
    times_correct INTEGER NOT NULL DEFAULT 0,
    last_result   TEXT NOT NULL,
    last_review   TEXT NOT NULL,           -- fecha y hora ISO
    next_review   TEXT NOT NULL            -- fecha ISO (AAAA-MM-DD)
);

CREATE TABLE IF NOT EXISTS answers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id TEXT NOT NULL,
    mode        TEXT NOT NULL,             -- estudio | tarjetas | repaso | examen
    result      TEXT NOT NULL,             -- no | parcial | bien
    user_answer TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exams (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL,
    unit_ids     TEXT NOT NULL,            -- lista JSON
    question_ids TEXT NOT NULL,            -- lista JSON
    status       TEXT NOT NULL,            -- en_curso | respondido | finalizado
    total        INTEGER NOT NULL,
    score        REAL,
    percentage   REAL,
    finished_at  TEXT
);

CREATE TABLE IF NOT EXISTS exam_answers (
    exam_id     INTEGER NOT NULL REFERENCES exams(id),
    question_id TEXT NOT NULL,
    user_answer TEXT NOT NULL DEFAULT '',
    result      TEXT,
    PRIMARY KEY (exam_id, question_id)
);
"""


def get_db_path() -> Path:
    """Permite cambiar la ruta con la variable SO_DB_PATH (usada por las pruebas)."""
    return Path(os.environ.get("SO_DB_PATH", DEFAULT_DB_PATH))


def get_connection() -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
