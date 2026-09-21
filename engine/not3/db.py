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
SCHEMA_VERSION = 2

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
        if current < 1:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        if current < 2:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(notes)").fetchall()]
            if "plus_notes" not in cols:
                conn.execute("ALTER TABLE notes ADD COLUMN plus_notes TEXT NOT NULL DEFAULT ''")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS note_comments (
                    id           INTEGER PRIMARY KEY,
                    note_id      INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
                    author       TEXT    NOT NULL DEFAULT 'User',
                    content      TEXT    NOT NULL,
                    timestamp_ms INTEGER,
                    created_at   TEXT    NOT NULL,
                    updated_at   TEXT    NOT NULL
                )"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_note ON note_comments (note_id, created_at)")
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
        conn.execute("DELETE FROM note_comments WHERE note_id = ?", (note_id,))
        conn.execute("DELETE FROM note_sections WHERE note_id = ?", (note_id,))
        conn.execute("DELETE FROM highlights WHERE note_id = ?", (note_id,))
        conn.execute("DELETE FROM findings WHERE note_id = ?", (note_id,))
        conn.execute("DELETE FROM lens_runs WHERE note_id = ?", (note_id,))
        conn.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))
        conn.execute("DELETE FROM jobs WHERE note_id = ?", (note_id,))
        conn.execute("DELETE FROM segments WHERE note_id = ?", (note_id,))
        conn.execute("DELETE FROM speakers WHERE note_id = ?", (note_id,))
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


def reset_stale_jobs(conn: sqlite3.Connection) -> int:
    """Reset any jobs left in 'running' state on startup and remove phantom embed jobs."""
    now = utcnow()
    with tx(conn):
        conn.execute("DELETE FROM jobs WHERE stage = 'embed'")
        cur = conn.execute(
            """UPDATE jobs
                  SET state = 'error', message = 'Interrupted', error = 'Processing was interrupted', finished_at = ?
                WHERE state = 'running'""",
            (now,),
        )
        conn.execute(
            """UPDATE notes
                  SET status = 'error', error = 'Processing was interrupted', updated_at = ?
                WHERE status = 'processing'""",
            (now,),
        )
        return cur.rowcount


def cancel_note_jobs(conn: sqlite3.Connection, note_id: int, reason: str = "Cancelled by user") -> None:
    """Mark all running or pending jobs for a note as cancelled/error."""
    now = utcnow()
    with tx(conn):
        conn.execute("DELETE FROM jobs WHERE note_id = ? AND stage = 'embed'", (note_id,))
        conn.execute(
            """UPDATE jobs
                  SET state = 'error', message = ?, error = ?, finished_at = ?
                WHERE note_id = ? AND state IN ('running', 'pending')""",
            (reason, reason, now, note_id),
        )
        conn.execute(
            """UPDATE notes
                  SET status = 'error', error = ?, updated_at = ?
                WHERE id = ? AND status != 'ready'""",
            (reason, now, note_id),
        )


def reset_note(conn: sqlite3.Connection, note_id: int) -> None:
    """Clear all errors and reset jobs for a note to a clean state."""
    now = utcnow()
    with tx(conn):
        conn.execute("DELETE FROM jobs WHERE note_id = ? AND stage = 'embed'", (note_id,))
        conn.execute("UPDATE jobs SET error = NULL WHERE note_id = ?", (note_id,))

        has_segments = conn.execute(
            "SELECT 1 FROM segments WHERE note_id = ? LIMIT 1", (note_id,)
        ).fetchone() is not None

        if has_segments:
            # Note already has transcript; reset subsequent stages that errored to pending
            conn.execute(
                """UPDATE jobs
                      SET state = 'pending', progress = 0.0, message = NULL, error = NULL, finished_at = NULL
                    WHERE note_id = ? AND stage NOT IN ('ingest', 'transcribe') AND state = 'error'""",
                (note_id,),
            )
            conn.execute(
                """UPDATE notes
                      SET status = 'ready', error = NULL, updated_at = ?
                    WHERE id = ?""",
                (now, note_id),
            )
        else:
            # Note does not have transcript; reset all stages to pending
            conn.execute(
                """UPDATE jobs
                      SET state = 'pending', progress = 0.0, message = NULL, error = NULL, finished_at = NULL
                    WHERE note_id = ? AND stage != 'ingest'""",
                (note_id,),
            )
            conn.execute(
                """UPDATE notes
                      SET status = 'new', error = NULL, updated_at = ?
                    WHERE id = ?""",
                (now, note_id),
            )


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


def upsert_section(conn: sqlite3.Connection, note_id: int, kind: str,
                   content_md: str, model: str | None = None) -> None:
    now = utcnow()
    with tx(conn):
        conn.execute(
            """INSERT INTO note_sections (note_id, kind, content_md, model, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (note_id, kind) DO UPDATE SET
                 content_md = excluded.content_md,
                 model = excluded.model,
                 created_at = excluded.created_at""",
            (note_id, kind, content_md, model or "user-edit", now),
        )


def get_plus_notes(conn: sqlite3.Connection, note_id: int) -> str:
    row = conn.execute("SELECT plus_notes FROM notes WHERE id = ?", (note_id,)).fetchone()
    return (row["plus_notes"] or "") if row else ""


def update_plus_notes(conn: sqlite3.Connection, note_id: int, content: str) -> None:
    now = utcnow()
    with tx(conn):
        conn.execute("UPDATE notes SET plus_notes = ?, updated_at = ? WHERE id = ?", (content, now, note_id))


def get_comments(conn: sqlite3.Connection, note_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT * FROM note_comments WHERE note_id = ? ORDER BY created_at ASC""",
        (note_id,),
    ).fetchall()


def create_comment(conn: sqlite3.Connection, *, note_id: int, content: str,
                   author: str = "User", timestamp_ms: int | None = None) -> int:
    now = utcnow()
    with tx(conn):
        cur = conn.execute(
            """INSERT INTO note_comments (note_id, author, content, timestamp_ms, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (note_id, author, content, timestamp_ms, now, now),
        )
    return int(cur.lastrowid)


def delete_comment(conn: sqlite3.Connection, comment_id: int) -> None:
    with tx(conn):
        conn.execute("DELETE FROM note_comments WHERE id = ?", (comment_id,))



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


# -- M7: Cross-note insights, actions & search ---------------------------


def get_all_action_items(conn: sqlite3.Connection) -> list[dict]:
    """Extract action items across all notes from note_sections."""
    rows = conn.execute(
        """SELECT ns.note_id, ns.content_md, ns.created_at, n.title, n.source_name
             FROM note_sections ns
             JOIN notes n ON n.id = ns.note_id
            WHERE ns.kind = 'action_items'
            ORDER BY ns.created_at DESC"""
    ).fetchall()

    actions = []
    item_id = 1
    for r in rows:
        note_id = r["note_id"]
        note_title = r["title"] or r["source_name"] or f"Note #{note_id}"
        created_at = r["created_at"]
        content = r["content_md"] or ""

        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip standard markdown bullet prefixes
            cleaned = line
            for prefix in ("- [ ]", "- [x]", "- ", "* ", "• "):
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):].strip()
                    break

            if not cleaned:
                continue

            # Detect assignee if formatted as "Assignee: Action" or "Name - Action"
            assignee = ""
            action_text = cleaned
            if ":" in cleaned and not cleaned.startswith("http"):
                parts = cleaned.split(":", 1)
                # If first part is reasonably short (a name/role)
                if len(parts[0].split()) <= 4:
                    assignee = parts[0].strip()
                    action_text = parts[1].strip()

            actions.append({
                "id": item_id,
                "note_id": note_id,
                "note_title": note_title,
                "assignee": assignee,
                "text": action_text,
                "raw": line,
                "completed": line.startswith("- [x]"),
                "created_at": created_at,
            })
            item_id += 1

    return actions


def get_pattern_matrix(conn: sqlite3.Connection) -> dict:
    """Aggregate findings by lens, category, speaker, and note across the library."""
    # Findings by lens
    by_lens = [
        {"lens_id": r["lens_id"], "count": r["cnt"]}
        for r in conn.execute(
            """SELECT lens_id, COUNT(*) AS cnt
                 FROM findings
                GROUP BY lens_id
                ORDER BY cnt DESC"""
        ).fetchall()
    ]

    # Findings by category
    by_category = [
        {"lens_id": r["lens_id"], "category": r["category"], "count": r["cnt"]}
        for r in conn.execute(
            """SELECT lens_id, category, COUNT(*) AS cnt
                 FROM findings
                GROUP BY lens_id, category
                ORDER BY cnt DESC"""
        ).fetchall()
    ]

    # Findings by speaker
    by_speaker = [
        {
            "speaker_name": r["speaker_name"] or r["speaker_label"] or "Unknown",
            "count": r["cnt"],
        }
        for r in conn.execute(
            """SELECT COALESCE(sp.display_name, sp.label, 'Unknown') AS speaker_name,
                      sp.label AS speaker_label,
                      COUNT(*) AS cnt
                 FROM findings f
                 LEFT JOIN speakers sp ON sp.id = f.speaker_id
                GROUP BY speaker_name
                ORDER BY cnt DESC"""
        ).fetchall()
    ]

    # Matrix: Lens + Category + Speaker
    matrix = [
        {
            "lens_id": r["lens_id"],
            "category": r["category"],
            "speaker_name": r["speaker_name"] or "Unknown",
            "count": r["cnt"],
        }
        for r in conn.execute(
            """SELECT f.lens_id, f.category,
                      COALESCE(sp.display_name, sp.label, 'Unknown') AS speaker_name,
                      COUNT(*) AS cnt
                 FROM findings f
                 LEFT JOIN speakers sp ON sp.id = f.speaker_id
                GROUP BY f.lens_id, f.category, speaker_name
                ORDER BY cnt DESC"""
        ).fetchall()
    ]

    total_findings = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    total_notes = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]

    return {
        "total_notes": total_notes,
        "total_findings": total_findings,
        "by_lens": by_lens,
        "by_category": by_category,
        "by_speaker": by_speaker,
        "matrix": matrix,
    }


def search_insights(
    conn: sqlite3.Connection,
    q: str | None = None,
    lens_id: str | None = None,
    category: str | None = None,
    speaker_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Multi-criteria search across segments and findings."""
    clauses = ["1=1"]
    params: list[object] = []

    if lens_id:
        clauses.append("f.lens_id = ?")
        params.append(lens_id)
    if category:
        clauses.append("f.category = ?")
        params.append(category)
    if speaker_id is not None:
        clauses.append("f.speaker_id = ?")
        params.append(speaker_id)
    if q and q.strip():
        clauses.append("(f.quote LIKE ? OR f.rationale LIKE ?)")
        wildcard = f"%{q.strip()}%"
        params.extend([wildcard, wildcard])

    where = " AND ".join(clauses)
    params.append(limit)

    sql = f"""SELECT f.id, f.note_id, f.lens_id, f.category, f.quote, f.confidence,
                     f.rationale, f.start_ms, f.end_ms, f.created_at,
                     n.title, n.source_name,
                     COALESCE(sp.display_name, sp.label, '') AS speaker_name
                FROM findings f
                JOIN notes n ON n.id = f.note_id
                LEFT JOIN speakers sp ON sp.id = f.speaker_id
               WHERE {where}
               ORDER BY f.created_at DESC
               LIMIT ?"""

    return rows_to_dicts(conn.execute(sql, params).fetchall())
