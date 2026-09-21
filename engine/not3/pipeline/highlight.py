"""Stage 5 — highlights.

The moments worth coming back to, as verbatim quotes bound to timestamps, so
clicking one plays the words it was taken from. Everything here goes through
the same anchoring gate as the lens findings.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from typing import TYPE_CHECKING

from ..config import Settings
from ..llm.anchor import Anchored, AnchorStats, anchor_items, dedupe
from ..llm.chunker import ChunkSegment, chunk_segments

if TYPE_CHECKING:
    from ..llm.ollama import Client

SYSTEM = (
    "You select the most significant moments in a transcript. You quote "
    "verbatim and never paraphrase inside a quote. You are selective: a "
    "highlight that is merely on-topic is not a highlight."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "highlights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "segment_id": {"type": "integer"},
                    "quote": {"type": "string"},
                    "reason": {"type": "string"},
                    "importance": {"type": "number"},
                },
                "required": ["segment_id", "quote", "reason", "importance"],
            },
        }
    },
    "required": ["highlights"],
}

PROMPT = """Below is part of a transcript. Each line is:

[segment_id] (timestamp) optional speaker: text

Select at most {max_items} moments from this part that someone reviewing the
recording would want to jump straight to. Prefer:

- decisions, commitments and conclusions
- a question or statement that changes the direction of the conversation
- something stated with unusual force, candour or emotion
- a concrete number, name, date or fact that matters

Skip pleasantries, filler, logistics and restatements of things already said.

For each: `segment_id` is the line, `quote` is copied **verbatim** from that
line, `reason` is one short clause on why it matters, and `importance` is
between 0 and 1.

If nothing in this part meets the bar, return an empty list. That is a correct
answer and is better than padding.

TRANSCRIPT
{transcript}"""


@dataclass
class HighlightResult:
    highlights: list[Anchored] = field(default_factory=list)
    stats: AnchorStats = field(default_factory=AnchorStats)
    model: str = ""


def find_highlights(
    segments: Sequence[ChunkSegment],
    settings: Settings,
    client: Client | None = None,
    *,
    max_per_chunk: int = 5,
    min_importance: float = 0.35,
    on_progress: Callable[[float, str], None] | None = None,
) -> HighlightResult:
    client = client or settings.llm_client()
    model = settings.model_highlight
    chunks = chunk_segments(
        segments,
        max_tokens=settings.chunk_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
    )
    if not chunks:
        return HighlightResult(model=model)

    found: list[Anchored] = []
    stats = AnchorStats()

    for chunk in chunks:
        if on_progress:
            on_progress(chunk.index / len(chunks),
                        f"highlighting part {chunk.index + 1}/{len(chunks)}")
        data = client.structured(
            model,
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": PROMPT.format(
                    transcript=chunk.render(), max_items=max_per_chunk
                )},
            ],
            SCHEMA,
            temperature=0.3,
        )

        items = list(data.get("highlights") or [])
        # `importance` is what this stage ranks on, so feed it to the gate as
        # the confidence value and let the shared threshold logic apply.
        for item in items:
            item["confidence"] = item.get("importance", 0.5)

        kept, chunk_stats = anchor_items(
            items, chunk,
            threshold=settings.quote_match_threshold,
            min_confidence=min_importance,
        )
        found.extend(kept)
        stats = stats.merge(chunk_stats)

    if on_progress:
        on_progress(1.0, "highlighted")

    return HighlightResult(
        highlights=dedupe(found),
        stats=stats,
        model=model,
    )
