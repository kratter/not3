from pathlib import Path
from fastapi.testclient import TestClient
from not3.api import create_app
from not3.config import Settings
from not3 import db


def test_auth_and_password_lifecycle(tmp_path: Path):
    s = Settings(data_dir=tmp_path)
    app = create_app(s)
    client = TestClient(app)

    # Initially no password set
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    assert r.json()["password_required"] is False

    # Setting password
    r = client.post("/api/auth/set_password", json={"password": "secure123"})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Password is now required
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    assert r.json()["password_required"] is True

    # Verifying wrong password fails
    r = client.post("/api/auth/verify", json={"password": "wrong"})
    assert r.status_code == 200
    assert r.json()["ok"] is False

    # Verifying correct password succeeds
    r = client.post("/api/auth/verify", json={"password": "secure123"})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Changing password with incorrect current password fails
    r = client.post("/api/auth/set_password", json={"password": "newpass", "current_password": "wrong"})
    assert r.status_code == 403

    # Changing password with correct current password succeeds
    r = client.post("/api/auth/set_password", json={"password": "newpass", "current_password": "secure123"})
    assert r.status_code == 200

    # Removing password
    r = client.post("/api/auth/remove_password", json={"current_password": "newpass"})
    assert r.status_code == 200

    # Password no longer required
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    assert r.json()["password_required"] is False


def test_comments_and_plus_notes_and_sections(tmp_path: Path):
    s = Settings(data_dir=tmp_path)
    app = create_app(s)
    client = TestClient(app)

    # Create a test note
    conn = db.get(s.db_path)
    note_id = db.create_note(
        conn,
        source_path="test.mp3",
        source_name="test.mp3",
        source_hash="testhash123",
        media_path="",
        duration_ms=60000,
        title="Session Alpha",
    )

    # 1. Plus Notes
    r = client.get(f"/api/notes/{note_id}/plus_notes")
    assert r.status_code == 200
    assert r.json()["plus_notes"] == ""

    r = client.put(f"/api/notes/{note_id}/plus_notes", json={"content": "Dr. Vance follow-up required next Monday."})
    assert r.status_code == 200
    assert r.json()["plus_notes"] == "Dr. Vance follow-up required next Monday."

    r = client.get(f"/api/notes/{note_id}")
    assert r.status_code == 200
    assert r.json()["plus_notes"] == "Dr. Vance follow-up required next Monday."

    # 2. Comments
    r = client.get(f"/api/notes/{note_id}/comments")
    assert r.status_code == 200
    assert r.json() == []

    r = client.post(
        f"/api/notes/{note_id}/comments",
        json={"content": "Important discussion about SQLite encryption", "author": "Reviewer", "timestamp_ms": 15000},
    )
    assert r.status_code == 200
    cmt = r.json()
    assert cmt["content"] == "Important discussion about SQLite encryption"
    assert cmt["timestamp_ms"] == 15000
    assert cmt["author"] == "Reviewer"

    # Fetch comments
    r = client.get(f"/api/notes/{note_id}/comments")
    assert r.status_code == 200
    assert len(r.json()) == 1

    # Delete comment
    r = client.delete(f"/api/notes/{note_id}/comments/{cmt['id']}")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.get(f"/api/notes/{note_id}/comments")
    assert r.status_code == 200
    assert len(r.json()) == 0

    # 3. Section updates
    r = client.put(
        f"/api/notes/{note_id}/sections/summary",
        json={"content_md": "Executive Summary: Full agreement on local architecture."},
    )
    assert r.status_code == 200
    assert r.json()["content_md"] == "Executive Summary: Full agreement on local architecture."

    # 4. Note Chat (fallback when Ollama is offline or mock test)
    r = client.post(
        f"/api/notes/{note_id}/chat",
        json={"prompt": "Reformat this note into bullet points"},
    )
    assert r.status_code == 200
    assert "reply" in r.json()
