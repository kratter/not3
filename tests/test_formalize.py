"""Test formalization, segmentation, and manual note creation."""

from __future__ import annotations

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from not3 import db
from not3.api import create_app
from not3.config import Settings
from not3.pipeline.formalize import formalize_notes, text_to_segments

TOKEN = "test-token"


def test_text_to_segments_plain():
    text = "First sentence here. Second sentence starts now! And a third?"
    segments, duration = text_to_segments(text)
    assert len(segments) == 3
    assert segments[0]["idx"] == 0
    assert segments[0]["text"] == "First sentence here."
    assert segments[1]["text"] == "Second sentence starts now!"
    assert segments[2]["text"] == "And a third?"
    assert segments[0]["start_ms"] == 0
    assert segments[0]["end_ms"] > 0
    assert segments[1]["start_ms"] > segments[0]["end_ms"]
    assert duration > segments[2]["end_ms"]


def test_text_to_segments_bullets_and_speakers():
    text = (
        "- discuss Q3 roadmap\n"
        "- finalize pricing model\n"
        "Alice: we should deploy on Friday.\n"
        "Bob: agreed, let's notify customer success."
    )
    segments, duration = text_to_segments(text)
    assert len(segments) == 4
    assert segments[0]["text"] == "discuss Q3 roadmap"
    assert segments[1]["text"] == "finalize pricing model"
    assert segments[2]["text"] == "we should deploy on Friday."
    assert segments[2]["_speaker"] == "Alice"
    assert segments[3]["text"] == "agreed, let's notify customer success."
    assert segments[3]["_speaker"] == "Bob"


def test_formalize_notes_mocked():
    class DummyClient:
        def chat(self, model, messages, **kwargs):
            return "The executive committee discussed the third quarter roadmap."

    out = formalize_notes("q3 roadmap discussion", client=DummyClient(), model="test-model")
    assert out == "The executive committee discussed the third quarter roadmap."


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NOT3_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NOT3_TOKEN", TOKEN)
    settings = Settings()
    settings.ensure_dirs()
    with TestClient(create_app(settings)) as c:
        yield c


def test_api_create_text_note_raw(client):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    payload = {
        "title": "Strategy Sync",
        "text": "- Launch product in October\n- Reach 100 enterprise pilots",
        "formalize": False,
        "run": False,
    }
    r = client.post("/api/notes/text", json=payload, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "note_id" in data
    assert data["duplicate"] is False

    note_id = data["note_id"]
    note_resp = client.get(f"/api/notes/{note_id}", headers=headers)
    assert note_resp.status_code == 200
    detail = note_resp.json()
    assert detail["note"]["title"] == "Strategy Sync"
    assert detail["note"]["asr_backend"] == "manual"
    assert detail["note"]["asr_model"] == "raw"

    segs = client.get(f"/api/notes/{note_id}/segments", headers=headers).json()
    assert len(segs) == 2
    assert segs[0]["text"] == "Launch product in October"
    assert segs[1]["text"] == "Reach 100 enterprise pilots"


def test_api_create_text_note_formalized(client):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    payload = {
        "title": "Architecture Memo",
        "text": "need faster cache redis maybe",
        "formalize": True,
        "style": "technical",
        "run": False,
    }

    with patch("not3.pipeline.formalize.formalize_notes", return_value="We should evaluate Redis to optimize cache latency."):
        r = client.post("/api/notes/text", json=payload, headers=headers)
        assert r.status_code == 200
        data = r.json()
        note_id = data["note_id"]

        note_resp = client.get(f"/api/notes/{note_id}", headers=headers).json()
        assert note_resp["note"]["asr_model"] == "formalized"

        segs = client.get(f"/api/notes/{note_id}/segments", headers=headers).json()
        assert len(segs) == 1
        assert "We should evaluate Redis" in segs[0]["text"]
