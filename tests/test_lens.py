"""Lens engine: loading, schema generation, and the filtering that happens
before anchoring. No model is called here — these are the parts that must
behave identically whatever the model does.
"""

from __future__ import annotations

import pytest

from not3.llm.chunker import Chunk, ChunkSegment, chunk_segments
from not3.pipeline.lens import LensError, parse_lens

MINIMAL = {
    "id": "test_lens",
    "name": "Test Lens",
    "version": 2,
    "categories": [
        {"id": "alpha", "label": "Alpha", "definition": "first",
         "positive_example": "yes", "negative_example": "no"},
        {"id": "beta", "definition": "second"},
    ],
    "thresholds": {"min_confidence": 0.7, "max_per_chunk": 3},
    "model": {"temperature": 0.1},
}


def test_parse_reads_every_field():
    lens = parse_lens(MINIMAL)
    assert (lens.id, lens.version, lens.min_confidence) == ("test_lens", 2, 0.7)
    assert lens.max_per_chunk == 3
    assert lens.temperature == 0.1
    assert lens.category_ids == ["alpha", "beta"]


def test_label_defaults_to_the_id():
    assert parse_lens(MINIMAL).categories[1].label == "beta"


@pytest.mark.parametrize("missing", ["id", "name", "categories"])
def test_incomplete_lens_is_rejected(missing):
    data = {k: v for k, v in MINIMAL.items() if k != missing}
    with pytest.raises(LensError):
        parse_lens(data)


def test_category_without_an_id_is_rejected():
    data = dict(MINIMAL, categories=[{"label": "no id here"}])
    with pytest.raises(LensError):
        parse_lens(data)


def test_schema_constrains_categories_to_the_lens():
    schema = parse_lens(MINIMAL).schema()
    props = schema["properties"]["findings"]["items"]["properties"]
    assert props["category"]["enum"] == ["alpha", "beta"]
    assert props["verdict"]["enum"] == ["instance", "near_miss"]
    assert "verdict" in schema["properties"]["findings"]["items"]["required"]


def test_prompt_carries_both_examples():
    """A near-miss example is the cheapest precision fix available, so it has
    to actually reach the model."""
    chunk = Chunk(index=0, segments=[
        ChunkSegment(id=1, start_ms=0, end_ms=1000, text="hello", speaker="A")
    ])
    prompt = parse_lens(MINIMAL).prompt(chunk)
    assert "counts:" in prompt and "does not count:" in prompt
    assert "[1]" in prompt and "hello" in prompt
    assert "near_miss" in prompt


def test_prompt_states_the_per_chunk_cap():
    chunk = Chunk(index=0, segments=[
        ChunkSegment(id=1, start_ms=0, end_ms=1000, text="hello")
    ])
    assert "at most 3" in parse_lens(MINIMAL).prompt(chunk)


# -- chunking -------------------------------------------------------------


def _segments(n: int, words: int = 40) -> list[ChunkSegment]:
    return [
        ChunkSegment(id=i, start_ms=i * 1000, end_ms=(i + 1) * 1000,
                     text=" ".join(["word"] * words))
        for i in range(n)
    ]


def test_short_transcript_is_one_chunk():
    chunks = chunk_segments(_segments(3), max_tokens=2500, overlap_tokens=200)
    assert len(chunks) == 1
    assert chunks[0].ids == {0, 1, 2}


def test_long_transcript_splits_and_every_segment_survives():
    segments = _segments(120)
    chunks = chunk_segments(segments, max_tokens=500, overlap_tokens=100)
    assert len(chunks) > 1
    covered = set().union(*(c.ids for c in chunks))
    assert covered == {s.id for s in segments}


def test_consecutive_chunks_overlap():
    """Overlap is what stops a pattern that straddles a boundary from being
    invisible in both chunks."""
    chunks = chunk_segments(_segments(120), max_tokens=500, overlap_tokens=150)
    assert chunks[0].ids & chunks[1].ids


def test_no_trailing_chunk_of_pure_overlap():
    for count in range(1, 60):
        chunks = chunk_segments(_segments(count), max_tokens=400, overlap_tokens=150)
        if len(chunks) > 1:
            assert not chunks[-1].ids <= chunks[-2].ids, f"{count} segments"


def test_empty_input_is_no_chunks():
    assert chunk_segments([], max_tokens=2500, overlap_tokens=200) == []


def test_render_includes_ids_and_speakers():
    chunk = Chunk(index=0, segments=[
        ChunkSegment(id=7, start_ms=65_000, end_ms=66_000, text="hi", speaker="Maya"),
    ])
    rendered = chunk.render()
    assert "[7]" in rendered and "Maya: hi" in rendered and "00:01:05" in rendered


def test_render_without_speakers_still_carries_the_id():
    chunk = Chunk(index=0, segments=[
        ChunkSegment(id=7, start_ms=0, end_ms=1000, text="hi"),
    ])
    assert "[7]" in chunk.render()
