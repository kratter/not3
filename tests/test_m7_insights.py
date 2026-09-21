"""Tests for Milestone 7 cross-note insights, custom lenses, and sample library."""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from not3.api import create_app
from not3.config import Settings
from not3 import db
from not3.sample_data import seed_sample_library, export_library_json, import_library_json


TOKEN = "test-token"


@pytest.fixture
def tmp_settings(tmp_path: Path, monkeypatch) -> Settings:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("NOT3_DATA_DIR", str(data_dir))
    monkeypatch.setenv("NOT3_TOKEN", TOKEN)

    s = Settings(data_dir=data_dir)
    s.ensure_dirs()
    return s


@pytest.fixture
def client(tmp_settings: Settings) -> TestClient:
    app = create_app(tmp_settings)
    c = TestClient(app)
    c.headers["authorization"] = f"Bearer {TOKEN}"
    return c


def test_seed_sample_library(tmp_settings: Settings):
    conn = db.get(tmp_settings.db_path)
    notes = seed_sample_library(conn, tmp_settings)
    assert len(notes) == 3
    # Check that segments were inserted
    segs = conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
    assert segs >= 25
    # Check that findings were inserted
    findings = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    assert findings >= 10
    # Check that action items exist in note_sections
    actions = db.get_all_action_items(conn)
    assert len(actions) >= 7
    # Check pattern matrix
    matrix = db.get_pattern_matrix(conn)
    assert matrix["total_findings"] >= 10
    assert len(matrix["by_lens"]) > 0
    assert len(matrix["by_speaker"]) > 0


def test_library_export_import(tmp_settings: Settings):
    conn = db.get(tmp_settings.db_path)
    seed_sample_library(conn, tmp_settings)
    pkg = export_library_json(conn)
    assert pkg["format"] == "not3_library"
    assert len(pkg["notes"]) == 3
    assert len(pkg["segments"]) >= 25

    # Test importing
    res = import_library_json(conn, pkg)
    assert "imported_notes" in res


def test_custom_lens_upload_and_delete(client: TestClient):
    valid_lens = """
id: custom_unit_test_lens
name: Unit Test Lens
version: 1
description: A test lens for unit verification
categories:
  - id: test_cat
    label: Test Category
    definition: Something being tested
    positive_example: "This is a positive test."
    negative_example: "This is a negative test."
"""
    # Upload
    res = client.post("/api/lenses", json={"yaml": valid_lens})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["id"] == "custom_unit_test_lens"
    assert data["name"] == "Unit Test Lens"

    # Fetch YAML
    res_yaml = client.get("/api/lenses/custom_unit_test_lens/yaml")
    assert res_yaml.status_code == 200
    assert "custom_unit_test_lens" in res_yaml.json()["yaml"]

    # Delete
    res_del = client.delete("/api/lenses/custom_unit_test_lens")
    assert res_del.status_code == 200
    assert res_del.json()["deleted"] == "custom_unit_test_lens"

    # Cannot delete built-in
    res_bad = client.delete("/api/lenses/cognitive_distortions")
    assert res_bad.status_code == 400


def test_sample_template_endpoint(client: TestClient):
    res = client.get("/api/lenses/sample-template")
    assert res.status_code == 200
    assert "strategic_alignment" in res.json()["yaml"] or "sample" in res.json()["yaml"]


def test_api_sample_seed_and_insights(client: TestClient):
    # Seed library via API
    res_seed = client.post("/api/library/sample")
    assert res_seed.status_code == 200
    assert res_seed.json()["seeded"] is True
    assert len(res_seed.json()["notes"]) == 3

    # Actions endpoint
    res_actions = client.get("/api/insights/actions")
    assert res_actions.status_code == 200
    actions = res_actions.json()
    assert len(actions) >= 7
    assert any("Dr. Vance" in a.get("assignee", "") or "Dr. Vance" in a.get("text", "") for a in actions)

    # Patterns endpoint
    res_patterns = client.get("/api/insights/patterns")
    assert res_patterns.status_code == 200
    patterns = res_patterns.json()
    assert patterns["total_findings"] >= 10

    # Search endpoint
    res_search = client.get("/api/insights/search?q=cloud")
    assert res_search.status_code == 200
    hits = res_search.json()
    assert len(hits) > 0

    # Ask endpoint (extractive fallback when Ollama not mock-loaded)
    res_ask = client.post("/api/insights/ask", json={"query": "What did they discuss about cloud sync and privacy?"})
    assert res_ask.status_code == 200
    ask_data = res_ask.json()
    assert "answer" in ask_data
    assert len(ask_data["citations"]) > 0
