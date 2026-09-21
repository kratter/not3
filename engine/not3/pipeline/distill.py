"""Stage 4 — distill a transcript into a note.

Map-reduce over chunks: each chunk is summarized on its own, then the partials
are merged into one note.

Key points and action items are quote-anchored like everything else. A summary
is prose and cannot be, but a claim that someone committed to do something is
exactly the kind of assertion that must be checkable, so each one carries the
words that imply it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from typing import TYPE_CHECKING

from ..config import Settings
from ..llm.anchor import Anchored, AnchorStats, anchor_items, dedupe
from ..llm.chunker import Chunk, ChunkSegment, chunk_segments

if TYPE_CHECKING:
    from ..llm.ollama import Client

SYSTEM = (
    "You summarize transcripts of real conversations. You are precise and you "
    "never invent content. If something is not in the transcript, it does not "
    "go in your output. An empty list is always a valid and correct answer."
)

CHUNK_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "segment_id": {"type": "integer"},
                    "quote": {"type": "string"},
                },
                "required": ["text", "segment_id", "quote"],
            },
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "owner": {"type": "string"},
                    "segment_id": {"type": "integer"},
                    "quote": {"type": "string"},
                },
                "required": ["text", "segment_id", "quote"],
            },
        },
        "topics": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "key_points", "action_items", "topics"],
}

REDUCE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "topics": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "summary", "topics"],
}

CHUNK_PROMPT = """Below is part of a transcript. Each line is:

[segment_id] (timestamp) optional speaker: text

Produce, using only what is in these lines:

- summary: 2-4 sentences on what is discussed in this part.
- key_points: the substantive points made. For each, `text` is your wording,
  `segment_id` is the line it comes from, and `quote` is copied **verbatim**
  from that line's text.
- action_items: only things someone actually committed to doing, or was asked
  to do. Not topics, not suggestions, not things merely discussed. `quote`
  must be copied verbatim from the cited line. If nobody committed to
  anything, return an empty list — this is common and correct.
- topics: 3-8 short subject labels.

Every quote must appear word for word in the line you cite. Do not paraphrase
inside a quote. Do not cite a segment_id that is not shown below.

TRANSCRIPT
{transcript}"""

REDUCE_PROMPT = """These are summaries of consecutive parts of one recording,
in order:

{partials}

Produce:
- title: a specific, concrete title for the whole recording, at most 8 words.
  No filler like "Discussion about" or "Meeting regarding".
- summary: 3-6 sentences covering the whole recording, in order, as a single
  paragraph. No bullet points, no preamble.
- topics: 5-10 short subject labels for the whole recording, deduplicated.

Use only what appears above."""


@dataclass
class DistillResult:
    title: str = ""
    summary: str = ""
    topics: list[str] = field(default_factory=list)
    key_points: list[Anchored] = field(default_factory=list)
    action_items: list[Anchored] = field(default_factory=list)
    stats: AnchorStats = field(default_factory=AnchorStats)
    model: str = ""


def distill(
    segments: Sequence[ChunkSegment],
    settings: Settings,
    client: Client | None = None,
    *,
    on_progress: Callable[[float, str], None] | None = None,
) -> DistillResult:
    client = client or settings.llm_client()
    model = settings.model_distill
    chunks = chunk_segments(
        segments,
        max_tokens=settings.chunk_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
    )
    if not chunks:
        return DistillResult(model=model)

    partials: list[str] = []
    key_points: list[Anchored] = []
    action_items: list[Anchored] = []
    topics: list[str] = []
    stats = AnchorStats()

    for chunk in chunks:
        if on_progress:
            on_progress(chunk.index / (len(chunks) + 1),
                        f"summarizing part {chunk.index + 1}/{len(chunks)}")
        data = client.structured(
            model,
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": CHUNK_PROMPT.format(transcript=chunk.render())},
            ],
            CHUNK_SCHEMA,
            temperature=0.2,
        )

        partials.append(str(data.get("summary") or "").strip())
        topics.extend(str(t).strip() for t in (data.get("topics") or []) if str(t).strip())

        kp, kp_stats = anchor_items(
            list(data.get("key_points") or []), chunk,
            threshold=settings.quote_match_threshold,
        )
        ai, ai_stats = anchor_items(
            list(data.get("action_items") or []), chunk,
            threshold=settings.quote_match_threshold,
        )
        key_points.extend(kp)
        action_items.extend(ai)
        stats = stats.merge(kp_stats).merge(ai_stats)

    result = DistillResult(
        key_points=dedupe(key_points),
        action_items=dedupe(action_items),
        stats=stats,
        model=model,
    )

    if on_progress:
        on_progress(len(chunks) / (len(chunks) + 1), "merging")

    if len(partials) == 1:
        result.summary = partials[0]
        result.topics = _dedupe_preserving_order(topics)[:10]
        result.title = _title_from(client, model, partials[0], result.topics)
    else:
        merged = client.structured(
            model,
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": REDUCE_PROMPT.format(
                    partials="\n\n".join(
                        f"Part {i + 1}: {p}" for i, p in enumerate(partials) if p
                    )
                )},
            ],
            REDUCE_SCHEMA,
            temperature=0.3,
        )
        result.title = str(merged.get("title") or "").strip()
        result.summary = str(merged.get("summary") or "").strip()
        result.topics = _dedupe_preserving_order(
            [str(t).strip() for t in (merged.get("topics") or [])] + topics
        )[:10]

    if on_progress:
        on_progress(1.0, "distilled")
    return result


def _title_from(client: Client, model: str, summary: str, topics: list[str]) -> str:
    """Single-chunk recordings skip the reduce pass, so they still need a title."""
    if not summary:
        return ""
    data = client.structured(
        model,
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content":
                "Give a specific, concrete title of at most 8 words for a recording "
                "with this summary. No filler openings like 'Discussion about'.\n\n"
                f"Summary: {summary}\nTopics: {', '.join(topics)}"},
        ],
        {"type": "object", "properties": {"title": {"type": "string"}},
         "required": ["title"]},
        temperature=0.3,
    )
    return str(data.get("title") or "").strip()


def _dedupe_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out
