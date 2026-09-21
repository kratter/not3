"""API surface: auth, shape, and the range handling the player depends on.

Runs against a throwaway data directory so it never touches the real library.
"""

from __future__ import annotations

import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from not3 import db
from not3.api import create_app
from not3.config import Settings

TOKEN = "test-token-not-a-secret"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NOT3_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NOT3_TOKEN", TOKEN)
    settings = Settings()
    settings.ensure_dirs()

    # A note with a real (tiny) wav so the audio route has something to serve.
    conn = db.get(settings.db_path)
    media = settings.media_dir / "sample.wav"
    media.write_bytes(_wav_bytes(2000))
    note_id = db.create_note(
        conn,
        source_path=str(media), source_name="sample.wav",
        source_hash="deadbeef", media_path=str(media),
        duration_ms=1000, title="Sample",
    )
    db.replace_segments(conn, note_id, [
        {"idx": 0, "start_ms": 0, "end_ms": 500, "text": "the quick brown fox",
         "confidence": 0.9, "words_json": None},
        {"idx": 1, "start_ms": 500, "end_ms": 1000, "text": "jumps over the lazy dog",
         "confidence": 0.8, "words_json": None},
    ])

    with TestClient(create_app(settings)) as c:
        c.note_id = note_id  # type: ignore[attr-defined]
        yield c


def _wav_bytes(data_len: int) -> bytes:
    import struct
    payload = b"\x00" * data_len
    return (
        b"RIFF" + struct.pack("<I", 36 + len(payload)) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
        + b"data" + struct.pack("<I", len(payload)) + payload
    )


def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


# -- auth -----------------------------------------------------------------


def test_health_needs_no_token(client):
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("path", ["/api/notes", "/api/status", "/api/lenses", "/api/search?q=x"])
def test_endpoints_refuse_without_a_token(client, path):
    assert client.get(path).status_code == 401


def test_wrong_token_is_refused(client):
    r = client.get("/api/notes", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_token_without_bearer_prefix_is_refused(client):
    assert client.get("/api/notes", headers={"Authorization": TOKEN}).status_code == 401


# -- notes ----------------------------------------------------------------


def test_notes_carry_their_counts(client):
    rows = client.get("/api/notes", headers=auth()).json()
    assert len(rows) == 1
    assert rows[0]["segment_count"] == 2
    assert rows[0]["highlight_count"] == 0


def test_note_detail_has_sections_and_jobs(client):
    body = client.get(f"/api/notes/{client.note_id}", headers=auth()).json()
    assert body["note"]["title"] == "Sample"
    assert "sections" in body and "jobs" in body and "speakers" in body


def test_missing_note_is_404(client):
    assert client.get("/api/notes/9999", headers=auth()).status_code == 404


def test_rename(client):
    r = client.patch(f"/api/notes/{client.note_id}",
                     headers=auth(), json={"title": "Renamed"})
    assert r.json()["title"] == "Renamed"


def test_unknown_stage_is_rejected(client):
    r = client.post(f"/api/notes/{client.note_id}/run",
                    headers=auth(), json={"stages": ["nonsense"]})
    assert r.status_code == 400


def test_import_of_a_missing_file_is_a_400_not_a_500(client):
    r = client.post("/api/notes/import", headers=auth(),
                    json={"path": "C:/definitely/not/here.mp3", "run": False})
    assert r.status_code == 400


# -- audio ----------------------------------------------------------------


def test_audio_is_served_whole(client):
    r = client.get(f"/api/notes/{client.note_id}/audio")
    assert r.status_code == 200
    assert r.headers["accept-ranges"] == "bytes"


def test_audio_range_returns_206_with_the_right_slice(client):
    """Seeking depends on this. Without 206 the player can only play from 0."""
    r = client.get(f"/api/notes/{client.note_id}/audio", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert len(r.content) == 100
    assert r.headers["content-range"].startswith("bytes 0-99/")


def test_open_ended_range_runs_to_the_end(client):
    full = client.get(f"/api/notes/{client.note_id}/audio").content
    r = client.get(f"/api/notes/{client.note_id}/audio", headers={"Range": "bytes=100-"})
    assert r.status_code == 206
    assert r.content == full[100:]


def test_suffix_range_returns_the_tail(client):
    full = client.get(f"/api/notes/{client.note_id}/audio").content
    r = client.get(f"/api/notes/{client.note_id}/audio", headers={"Range": "bytes=-50"})
    assert r.status_code == 206
    assert r.content == full[-50:]


def test_range_past_the_end_is_clamped(client):
    size = len(client.get(f"/api/notes/{client.note_id}/audio").content)
    r = client.get(f"/api/notes/{client.note_id}/audio",
                   headers={"Range": f"bytes=0-{size + 10_000}"})
    assert r.status_code == 206
    assert len(r.content) == size


# -- search ---------------------------------------------------------------


def test_search_finds_a_segment(client):
    hits = client.get("/api/search?q=brown", headers=auth()).json()
    assert len(hits) == 1
    assert hits[0]["note_id"] == client.note_id


def test_search_marks_matches_without_html(client):
    """The snippet must not carry markup — the client renders it as text."""
    snippet = client.get("/api/search?q=brown", headers=auth()).json()[0]["snippet"]
    assert "\x02" in snippet and "\x03" in snippet
    assert "<" not in snippet


def test_search_does_not_choke_on_fts_syntax(client):
    """Users type quotes and operators; those are input, not query syntax."""
    for term in ['"', "AND", "fox OR dog", "NEAR(", "*"]:
        r = client.get("/api/search", params={"q": term}, headers=auth())
        assert r.status_code == 200, f"{term!r} produced {r.status_code}"


def test_blank_search_returns_nothing(client):
    assert client.get("/api/search?q=  ", headers=auth()).json() == []


# -- lenses ---------------------------------------------------------------


def test_lenses_are_registered_on_startup(client):
    lenses = client.get("/api/lenses", headers=auth()).json()
    ids = {l["id"] for l in lenses}
    assert {"cognitive_distortions", "emotional_arc", "communication_patterns"} <= ids
    assert all(l["builtin"] for l in lenses)


def test_disabling_a_lens_sticks(client):
    client.patch("/api/lenses/emotional_arc", headers=auth(), json={"enabled": False})
    lenses = {l["id"]: l for l in client.get("/api/lenses", headers=auth()).json()}
    assert lenses["emotional_arc"]["enabled"] is False
    assert lenses["cognitive_distortions"]["enabled"] is True


def test_patching_an_unknown_lens_is_404(client):
    r = client.patch("/api/lenses/no_such_lens", headers=auth(), json={"enabled": True})
    assert r.status_code == 404
