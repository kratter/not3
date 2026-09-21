import sqlite3
from pathlib import Path

import pytest
from not3.config import Settings
from not3.pipeline.diarize import (
    DiarizerBackend,
    SherpaDiarizer,
    SpeakerTurn,
    align_segments_to_speakers,
    diarize_note,
)


def test_align_segments_exact_overlap():
    segments = [
        {"id": 1, "start_ms": 0, "end_ms": 1000},
        {"id": 2, "start_ms": 1200, "end_ms": 2500},
    ]
    turns = [
        SpeakerTurn(start_ms=0, end_ms=1000, speaker="SPEAKER_00"),
        SpeakerTurn(start_ms=1100, end_ms=3000, speaker="SPEAKER_01"),
    ]
    alignment = align_segments_to_speakers(segments, turns)
    assert alignment[1] == "SPEAKER_00"
    assert alignment[2] == "SPEAKER_01"


def test_align_segments_dominant_overlap():
    # Segment spans two speakers, 70% speaker 1, 30% speaker 2
    segments = [
        {"id": 10, "start_ms": 1000, "end_ms": 2000},
    ]
    turns = [
        SpeakerTurn(start_ms=500, end_ms=1300, speaker="SPEAKER_00"),  # 300 ms overlap
        SpeakerTurn(start_ms=1300, end_ms=2500, speaker="SPEAKER_01"), # 700 ms overlap
    ]
    alignment = align_segments_to_speakers(segments, turns)
    assert alignment[10] == "SPEAKER_01"


def test_align_segments_fallback_proximity():
    # Segment in a small gap between turns
    segments = [
        {"id": 20, "start_ms": 1050, "end_ms": 1150},
    ]
    turns = [
        SpeakerTurn(start_ms=0, end_ms=1000, speaker="SPEAKER_00"),  # 50 ms away
        SpeakerTurn(start_ms=5000, end_ms=6000, speaker="SPEAKER_01"),
    ]
    alignment = align_segments_to_speakers(segments, turns)
    assert alignment[20] == "SPEAKER_00"


def test_align_segments_empty_inputs():
    assert align_segments_to_speakers([], []) == {}
    assert align_segments_to_speakers([{"id": 1, "start_ms": 0, "end_ms": 500}], []) == {}


def test_diarize_off(tmp_path: Path):
    s = Settings(data_dir=tmp_path, diarizer="off")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    assert diarize_note(conn, 1, s) == 0


def test_sherpa_diarizer_on_fixture(tmp_path: Path):
    s = Settings()
    if not s.diarize_segmentation_path().is_file() or not s.diarize_embedding_path().is_file():
        pytest.skip("Diarization models not downloaded")

    diarizer = SherpaDiarizer(s)
    fixture_wav = Path(__file__).parent / "fixtures" / "jfk.wav"
    assert fixture_wav.is_file()

    turns = diarizer.diarize(fixture_wav)
    assert len(turns) > 0
    # jfk.wav is a single speaker speech
    speakers = {t.speaker for t in turns}
    assert len(speakers) == 1
    assert "SPEAKER_00" in speakers


def test_diarize_note_integration(tmp_path: Path):
    from not3 import db

    schema_sql = (Path(__file__).resolve().parents[1] / "engine" / "not3" / "schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(schema_sql)

    wav = tmp_path / "dummy.wav"
    wav.write_bytes(b"RIFFdummyWAVE")

    note_id = db.create_note(
        conn,
        source_path=str(wav),
        source_name="dummy.wav",
        source_hash="dummyhash",
        media_path=str(wav),
        duration_ms=4000,
        title="Test",
    )
    db.replace_segments(conn, note_id, [
        {"idx": 0, "start_ms": 0, "end_ms": 2000, "text": "Hello world", "confidence": 1.0, "words_json": None},
        {"idx": 1, "start_ms": 2000, "end_ms": 4000, "text": "Good morning", "confidence": 1.0, "words_json": None},
    ])

    class MockDiarizer:
        def diarize(self, media_path, progress_cb=None):
            return [
                SpeakerTurn(start_ms=0, end_ms=2000, speaker="SPEAKER_00"),
                SpeakerTurn(start_ms=2000, end_ms=4000, speaker="SPEAKER_01"),
            ]

    s = Settings(data_dir=tmp_path)
    count = diarize_note(conn, note_id, s, diarizer=MockDiarizer())
    assert count == 2

    speakers = conn.execute("SELECT label FROM speakers WHERE note_id = ?", (note_id,)).fetchall()
    assert {r["label"] for r in speakers} == {"SPEAKER_00", "SPEAKER_01"}

    segs = conn.execute("SELECT s.idx, sp.label FROM segments s JOIN speakers sp ON s.speaker_id = sp.id WHERE s.note_id = ? ORDER BY s.idx", (note_id,)).fetchall()
    assert segs[0]["label"] == "SPEAKER_00"
    assert segs[1]["label"] == "SPEAKER_01"
