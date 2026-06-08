import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "history.db")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id    TEXT    UNIQUE,
                title       TEXT,
                duration    INTEGER,
                url         TEXT,
                total_shorts INTEGER,
                created_at  TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS shorts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id     TEXT,
                rank         INTEGER,
                label        TEXT,
                start        REAL,
                end          REAL,
                duration     REAL,
                effect       TEXT,
                clip_file    TEXT,
                download_url TEXT,
                is_best      INTEGER
            )
        """)
        c.commit()


def save_result(video_id: str, title: str, duration: int, url: str, shorts: list):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO videos "
            "(video_id, title, duration, url, total_shorts, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (video_id, title, duration, url, len(shorts),
             datetime.utcnow().isoformat()),
        )
        c.execute("DELETE FROM shorts WHERE video_id=?", (video_id,))
        for s in shorts:
            c.execute(
                "INSERT INTO shorts "
                "(video_id, rank, label, start, end, duration, "
                " effect, clip_file, download_url, is_best) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    video_id, s["rank"], s["label"],
                    s["start"], s["end"], s["duration"],
                    s.get("effect", "none"),
                    s.get("clip_file", ""),
                    s.get("download_url", ""),
                    1 if s.get("is_best") else 0,
                ),
            )
        c.commit()


def get_history(limit: int = 20) -> list:
    with _conn() as c:
        rows = c.execute(
            "SELECT video_id, title, duration, url, total_shorts, created_at "
            "FROM videos ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_video_shorts(video_id: str) -> dict | None:
    with _conn() as c:
        v = c.execute(
            "SELECT * FROM videos WHERE video_id=?", (video_id,)
        ).fetchone()
        if not v:
            return None
        shorts = c.execute(
            "SELECT * FROM shorts WHERE video_id=? ORDER BY rank", (video_id,)
        ).fetchall()
    return {
        "video_id": video_id,
        "title": v["title"],
        "duration": v["duration"],
        "total_shorts": v["total_shorts"],
        "shorts": [dict(s) for s in shorts],
    }
