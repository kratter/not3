"""SQLite access.

One connection per thread, WAL so the API can read while the pipeline writes,
and foreign keys on so the "every finding points at a real segment" invariant
is enforced by the database rather than by hope.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_VERSION = 1

_local = threading.local()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]


def connect(db_path: Path) -> sqlite3.Connection:
    """Open (and on first use, create) the database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current >= SCHEMA_VERSION:
        return
    with conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def get(db_path: Path) -> sqlite3.Connection:
    """Thread-local connection. SQLite objects are not safe to share."""
    key = str(db_path)
    cache: dict[str, sqlite3.Connection] = getattr(_local, "conns", None) or {}
    if not hasattr(_local, "conns"):
        _local.conns = cache
    conn = cache.get(key)
    if conn is None:
        conn = connect(db_path)
        cache[key] = conn
    return conn


@contextmanager
def tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Explicit transaction. `with conn` alone does not begin one for reads."""
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()


# -- notes ----------------------------------------------------------------


def find_note_by_hash(conn: sqlite3.Connection, source_hash: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM notes WHERE source_hash = ?", (source_hash,)
    ).fetchone()


def create_note(
    conn: sqlite3.Connection,
    *,
    source_path: str,
    source_name: str,
    source_hash: str,
    media_path: str,
    duration_ms: int,
    title: str = "",
) -> int:
    now = utcnow()
    with tx(conn):
        cur = conn.execute(
            """INSERT INTO notes
                 (title, source_path, source_name, source_hash, media_path,
                  duration_ms, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'new', ?, ?)""",
            (title, source_path, source_name, source_hash, media_path,
             duration_ms, now, now),
        )
    return int(cur.lastrowid)


def update_note(conn: sqlite3.Connection, note_id: int, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = utcnow()
    sets = ", ".join(f"{k} = ?" for k in fields)
    with tx(conn):
        conn.execute(
            f"UPDATE notes SET {sets} WHERE id = ?", (*fields.values(), note_id)
        )


def get_note(conn: sqlite3.Connection, note_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()


def list_notes(conn: sqlite3.Connection, limit: int = 200) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM notes ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()


def delete_note(conn: sqlite3.Connection, note_id: int) -> None:
    with tx(conn):
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))


# -- segments -------------------------------------------------------------


def replace_segments(conn: sqlite3.Connection, note_id: int, rows: list[dict]) -> int:
    """Write a note's segments, replacing any previous transcription."""
    with tx(conn):
        conn.execute("DELETE FROM segments WHERE note_id = ?", (note_id,))
        conn.executemany(
            """INSERT INTO segments
                 (note_id, idx, start_ms, end_ms, text, confidence, words_json)
               VALUES (:note_id, :idx, :start_ms, :end_ms, :text, :confidence, :words_json)""",
            [{"note_id": note_id, **r} for r in rows],
        )
    return len(rows)


def get_segments(conn: sqlite3.Connection, note_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT s.*, sp.label AS speaker_label, sp.display_name AS speaker_name
             FROM segments s
             LEFT JOIN speakers sp ON sp.id = s.speaker_id
            WHERE s.note_id = ?
            ORDER BY s.idx""",
        (note_id,),
    ).fetchall()


# -- jobs -----------------------------------------------------------------

STAGES = (
    "ingest",
    "transcribe",
    "diarize",
    "distill",
    "highlight",
    "lens",
    "embed",
    "export",
)


def init_jobs(conn: sqlite3.Connection, note_id: int) -> None:
    with tx(conn):
        conn.executemany(
            """INSERT INTO jobs (note_id, stage, state) VALUES (?, ?, 'pending')
               ON CONFLICT (note_id, stage) DO NOTHING""",
            [(note_id, s) for s in STAGES],
        )


def set_job(
    conn: sqlite3.Connection,
    note_id: int,
    stage: str,
    *,
    state: str | None = None,
    progress: float | None = None,
    message: str | None = None,
    error: str | None = None,
) -> None:
    fields: dict[str, object] = {}
    if state is not None:
        fields["state"] = state
        if state == "running":
            fields["started_at"] = utcnow()
        elif state in {"done", "error", "skipped"}:
            fields["finished_at"] = utcnow()
    if progress is not None:
        fields["progress"] = progress
    if message is not None:
        fields["message"] = message
    if error is not None:
        fields["error"] = error
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    with tx(conn):
        conn.execute(
            f"""INSERT INTO jobs (note_id, stage, state) VALUES (?, ?, 'pending')
                ON CONFLICT (note_id, stage) DO NOTHING""",
            (note_id, stage),
        )
        conn.execute(
            f"UPDATE jobs SET {sets} WHERE note_id = ? AND stage = ?",
            (*fields.values(), note_id, stage),
        )


def get_jobs(conn: sqlite3.Connection, note_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM jobs WHERE note_id = ? ORDER BY id", (note_id,)
    ).fetchall()


# -- sections, highlights, findings ---------------------------------------


def replace_sections(conn: sqlite3.Connection, note_id: int, sections: dict[str, str],
                     model: str) -> None:
    """Write the distilled note. Replaces any previous run for this note."""
    now = utcnow()
    with tx(conn):
        conn.execute("DELETE FROM note_sections WHERE note_id = ?", (note_id,))
        conn.executemany(
            """INSERT INTO note_sections (note_id, kind, content_md, model, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            [(note_id, kind, content, model, now)
             for kind, content in sections.items() if content],
        )


def get_sections(conn: sqlite3.Connection, note_id: int) -> dict[str, str]:
    rows = conn.execute(
        "SELECT kind, content_md FROM note_sections WHERE note_id = ?", (note_id,)
    ).fetchall()
    return {r["kind"]: r["content_md"] for r in rows}


def replace_highlights(conn: sqlite3.Connection, note_id: int, rows: list[dict],
                       model: str) -> int:
    """Replace auto highlights, leaving anything the user marked by hand."""
    now = utcnow()
    with tx(conn):
        conn.execute(
            "DELETE FROM highlights WHERE note_id = ? AND kind = 'auto'", (note_id,)
        )
        conn.executemany(
            """INSERT INTO highlights
                 (note_id, segment_id, start_ms, end_ms, quote, kind, reason,
                  importance, model, created_at)
               VALUES (?, ?, ?, ?, ?, 'auto', ?, ?, ?, ?)""",
            [(note_id, r["segment_id"], r["start_ms"], r["end_ms"], r["quote"],
              r.get("reason"), r.get("importance"), model, now) for r in rows],
        )
    return len(rows)


def get_highlights(conn: sqlite3.Connection, note_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM highlights WHERE note_id = ? ORDER BY start_ms", (note_id,)
    ).fetchall()


def replace_findings(conn: sqlite3.Connection, note_id: int, lens_id: str,
                     rows: list[dict], model: str) -> int:
    now = utcnow()
    with tx(conn):
        conn.execute(
            "DELETE FROM findings WHERE note_id = ? AND lens_id = ?", (note_id, lens_id)
        )
        conn.executemany(
            """INSERT INTO findings
                 (note_id, lens_id, lens_version, category, quote, segment_id,
                  start_ms, end_ms, speaker_id, confidence, rationale, model, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(note_id, lens_id, r["lens_version"], r["category"], r["quote"],
              r["segment_id"], r["start_ms"], r["end_ms"], r.get("speaker_id"),
              r["confidence"], r.get("rationale"), model, now) for r in rows],
        )
    return len(rows)


def get_findings(conn: sqlite3.Connection, note_id: int,
                 lens_id: str | None = None) -> list[sqlite3.Row]:
    if lens_id:
        return conn.execute(
            "SELECT * FROM findings WHERE note_id = ? AND lens_id = ? ORDER BY start_ms",
            (note_id, lens_id),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM findings WHERE note_id = ? ORDER BY lens_id, start_ms", (note_id,)
    ).fetchall()


def record_lens_run(conn: sqlite3.Connection, note_id: int, lens_id: str,
                    lens_version: int, model: str, stats, duration_ms: int) -> None:
    """Persist anchoring telemetry. The drop rate is how a lens is judged."""
    with tx(conn):
        conn.execute(
            """INSERT INTO lens_runs
                 (note_id, lens_id, lens_version, model, proposed, kept,
                  dropped_no_segment, dropped_no_quote, dropped_low_conf,
                  duration_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (note_id, lens_id, lens_version, model, stats.proposed, stats.kept,
             stats.dropped_no_segment, stats.dropped_no_quote,
             stats.dropped_low_conf, duration_ms, utcnow()),
        )
