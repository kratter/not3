-- Not3 schema.
--
-- Invariant that the whole design rests on: every highlight and every finding
-- references a real segment and a real time range, so anything the app claims
-- can be clicked and played back. That is enforced here with NOT NULL foreign
-- keys, not only in application code.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS notes (
    id           INTEGER PRIMARY KEY,
    title        TEXT    NOT NULL DEFAULT '',
    source_path  TEXT    NOT NULL,          -- original file as the user gave it
    source_name  TEXT    NOT NULL,
    source_hash  TEXT    NOT NULL UNIQUE,   -- sha256, dedupes re-imports
    media_path   TEXT,                      -- normalized 16 kHz mono wav
    duration_ms  INTEGER NOT NULL DEFAULT 0,
    language     TEXT,
    status       TEXT    NOT NULL DEFAULT 'new'
                 CHECK (status IN ('new', 'processing', 'ready', 'error')),
    asr_backend  TEXT,                      -- cuda | metal | cpu
    asr_model    TEXT,
    error        TEXT,
    plus_notes   TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS speakers (
    id           INTEGER PRIMARY KEY,
    note_id      INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    label        TEXT    NOT NULL,          -- SPEAKER_00, from the diarizer
    display_name TEXT,                      -- what the user renamed it to
    UNIQUE (note_id, label)
);

CREATE TABLE IF NOT EXISTS segments (
    id         INTEGER PRIMARY KEY,
    note_id    INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    idx        INTEGER NOT NULL,            -- ordinal within the note
    start_ms   INTEGER NOT NULL,
    end_ms     INTEGER NOT NULL,
    text       TEXT    NOT NULL,
    speaker_id INTEGER REFERENCES speakers (id) ON DELETE SET NULL,
    confidence REAL,
    words_json TEXT,                        -- word timings, kept inline: too
                                            -- granular to be worth its own table
    UNIQUE (note_id, idx)
);

CREATE INDEX IF NOT EXISTS idx_segments_note_time ON segments (note_id, start_ms);
CREATE INDEX IF NOT EXISTS idx_segments_speaker ON segments (speaker_id);

CREATE TABLE IF NOT EXISTS note_sections (
    id         INTEGER PRIMARY KEY,
    note_id    INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    kind       TEXT    NOT NULL
               CHECK (kind IN ('summary', 'key_points', 'action_items', 'topics')),
    content_md TEXT    NOT NULL,
    model      TEXT,
    created_at TEXT    NOT NULL,
    UNIQUE (note_id, kind)
);

CREATE TABLE IF NOT EXISTS highlights (
    id         INTEGER PRIMARY KEY,
    note_id    INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    segment_id INTEGER NOT NULL REFERENCES segments (id) ON DELETE CASCADE,
    start_ms   INTEGER NOT NULL,
    end_ms     INTEGER NOT NULL,
    quote      TEXT    NOT NULL,
    kind       TEXT    NOT NULL DEFAULT 'auto' CHECK (kind IN ('auto', 'manual')),
    reason     TEXT,
    importance REAL,
    model      TEXT,
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_highlights_note ON highlights (note_id, start_ms);

-- Registry of lens YAML files, synced from disk on startup.
CREATE TABLE IF NOT EXISTS lenses (
    id          TEXT    PRIMARY KEY,        -- the `id` field in the YAML
    name        TEXT    NOT NULL,
    version     INTEGER NOT NULL,
    description TEXT,
    path        TEXT    NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    disclaimer  TEXT,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id           INTEGER PRIMARY KEY,
    note_id      INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    lens_id      TEXT    NOT NULL,
    lens_version INTEGER NOT NULL,          -- so findings from an edited lens
                                            -- remain distinguishable
    category     TEXT    NOT NULL,
    quote        TEXT    NOT NULL,          -- verbatim, validated against the segment
    segment_id   INTEGER NOT NULL REFERENCES segments (id) ON DELETE CASCADE,
    start_ms     INTEGER NOT NULL,
    end_ms       INTEGER NOT NULL,
    speaker_id   INTEGER REFERENCES speakers (id) ON DELETE SET NULL,
    confidence   REAL    NOT NULL,
    rationale    TEXT,
    model        TEXT,
    created_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_findings_note ON findings (note_id, start_ms);
CREATE INDEX IF NOT EXISTS idx_findings_lens ON findings (lens_id, category);

-- Anchoring telemetry. The drop rate is how you tell a good lens from a bad
-- one, and how you compare models on your own data, so it is first-class here
-- rather than a log line.
CREATE TABLE IF NOT EXISTS lens_runs (
    id                 INTEGER PRIMARY KEY,
    note_id            INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    lens_id            TEXT    NOT NULL,
    lens_version       INTEGER NOT NULL,
    model              TEXT    NOT NULL,
    proposed           INTEGER NOT NULL,    -- what the model returned
    kept               INTEGER NOT NULL,    -- what survived anchoring
    dropped_no_segment INTEGER NOT NULL DEFAULT 0,
    dropped_no_quote   INTEGER NOT NULL DEFAULT 0,
    dropped_low_conf   INTEGER NOT NULL DEFAULT 0,
    duration_ms        INTEGER,
    created_at         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS note_tags (
    note_id INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);

-- One row per pipeline stage per note. Drives both resumability and the
-- progress the UI streams over SSE.
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY,
    note_id     INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    stage       TEXT    NOT NULL,
    state       TEXT    NOT NULL DEFAULT 'pending'
                CHECK (state IN ('pending', 'running', 'done', 'error', 'skipped')),
    progress    REAL    NOT NULL DEFAULT 0,
    message     TEXT,
    error       TEXT,
    started_at  TEXT,
    finished_at TEXT,
    UNIQUE (note_id, stage)
);

CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts
    USING fts5 (text, content = 'segments', content_rowid = 'id', tokenize = 'porter unicode61');

CREATE TRIGGER IF NOT EXISTS segments_ai AFTER INSERT ON segments BEGIN
    INSERT INTO segments_fts (rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS segments_ad AFTER DELETE ON segments BEGIN
    INSERT INTO segments_fts (segments_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS segments_au AFTER UPDATE ON segments BEGIN
    INSERT INTO segments_fts (segments_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO segments_fts (rowid, text) VALUES (new.id, new.text);
END;

CREATE TABLE IF NOT EXISTS note_comments (
    id           INTEGER PRIMARY KEY,
    note_id      INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    author       TEXT    NOT NULL DEFAULT 'User',
    content      TEXT    NOT NULL,
    timestamp_ms INTEGER,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_comments_note ON note_comments (note_id, created_at);

