"""Windowing a transcript into model-sized chunks.

A 90-minute recording does not fit in any local model's context. Everything
downstream therefore works on chunks, and every chunk carries its segment ids
so results can be anchored back to real audio.

The segment id is the join key between the model's output and the database,
which is why it is rendered into the prompt text itself rather than left
implicit in the ordering.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

# English averages ~4 characters per token; transcripts skew slightly lower
# because of short function words. Good enough for windowing — we are sizing
# batches, not billing for them.
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class ChunkSegment:
    id: int
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None = None


@dataclass
class Chunk:
    index: int
    segments: list[ChunkSegment] = field(default_factory=list)

    @property
    def ids(self) -> set[int]:
        return {s.id for s in self.segments}

    @property
    def start_ms(self) -> int:
        return self.segments[0].start_ms if self.segments else 0

    @property
    def end_ms(self) -> int:
        return self.segments[-1].end_ms if self.segments else 0

    def render(self, *, with_speakers: bool = True) -> str:
        """The transcript as the model sees it.

        One segment per line, id first. Keeping the id adjacent to the text it
        labels is what makes the model reliably able to cite it.
        """
        lines = []
        for s in self.segments:
            stamp = _hhmmss(s.start_ms)
            if with_speakers and s.speaker:
                lines.append(f"[{s.id}] ({stamp}) {s.speaker}: {s.text}")
            else:
                lines.append(f"[{s.id}] ({stamp}) {s.text}")
        return "\n".join(lines)

    def lookup(self) -> dict[int, ChunkSegment]:
        return {s.id: s for s in self.segments}


def _hhmmss(ms: int) -> str:
    s = int(ms) // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def to_chunk_segments(rows: Sequence[Any]) -> list[ChunkSegment]:
    """Adapt sqlite3.Row segments (or dicts) into chunker input."""
    out: list[ChunkSegment] = []
    for r in rows:
        get = r.__getitem__ if not isinstance(r, dict) else r.get
        try:
            speaker = get("speaker_name") or get("speaker_label")
        except (KeyError, IndexError):
            speaker = None
        out.append(
            ChunkSegment(
                id=int(get("id")),
                start_ms=int(get("start_ms")),
                end_ms=int(get("end_ms")),
                text=str(get("text")),
                speaker=speaker,
            )
        )
    return out


def chunk_segments(
    segments: Sequence[ChunkSegment],
    *,
    max_tokens: int = 2500,
    overlap_tokens: int = 200,
) -> list[Chunk]:
    """Split segments into overlapping windows.

    Overlap exists so a pattern spanning a boundary is visible whole in at
    least one chunk. Duplicates it creates are removed in the reduce step,
    where they are cheap — a missed finding is not recoverable, a duplicate is.
    """
    if not segments:
        return []

    chunks: list[Chunk] = []
    current: list[ChunkSegment] = []
    current_tokens = 0

    for seg in segments:
        cost = estimate_tokens(seg.text) + 8  # id, timestamp and speaker prefix
        if current and current_tokens + cost > max_tokens:
            chunks.append(Chunk(index=len(chunks), segments=list(current)))
            current, current_tokens = _tail(current, overlap_tokens)
        current.append(seg)
        current_tokens += cost

    if current:
        # Avoid emitting a final chunk that is nothing but overlap.
        if chunks and set(s.id for s in current) <= chunks[-1].ids:
            return chunks
        chunks.append(Chunk(index=len(chunks), segments=list(current)))
    return chunks


def _tail(segments: list[ChunkSegment], overlap_tokens: int) -> tuple[list[ChunkSegment], int]:
    """The trailing slice of a chunk to carry into the next one."""
    if overlap_tokens <= 0:
        return [], 0
    tail: list[ChunkSegment] = []
    total = 0
    for seg in reversed(segments):
        cost = estimate_tokens(seg.text) + 8
        if total + cost > overlap_tokens:
            break
        tail.insert(0, seg)
        total += cost
    return tail, total
