"""The anchoring gate.

Every highlight and every lens finding must be traceable to words that were
actually spoken. A JSON schema makes the model's output well-shaped; it says
nothing about whether the quote inside it is real. This module is what decides
that, and it is the reason the pattern-recognition features are defensible
rather than decorative.

Three outcomes per proposed item:

  kept        the quote occurs in the cited segment
  relocated   the quote occurs in the chunk, but in a different segment than
              cited — real speech, wrong citation, so we fix the citation and
              count it rather than throwing away a true observation
  dropped     the quote does not occur anywhere in what the model was shown,
              its segment is not in the chunk, or its confidence is too low

Drop rates are returned, not logged and forgotten: they are how you tell a
sharp lens from a sloppy one, and how you compare two models on your own data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

from .chunker import Chunk, ChunkSegment


@dataclass
class AnchorStats:
    proposed: int = 0
    kept: int = 0
    relocated: int = 0
    dropped_no_segment: int = 0
    dropped_no_quote: int = 0
    dropped_low_conf: int = 0

    @property
    def dropped(self) -> int:
        return self.dropped_no_segment + self.dropped_no_quote + self.dropped_low_conf

    @property
    def drop_rate(self) -> float:
        return self.dropped / self.proposed if self.proposed else 0.0

    def merge(self, other: "AnchorStats") -> "AnchorStats":
        return AnchorStats(
            proposed=self.proposed + other.proposed,
            kept=self.kept + other.kept,
            relocated=self.relocated + other.relocated,
            dropped_no_segment=self.dropped_no_segment + other.dropped_no_segment,
            dropped_no_quote=self.dropped_no_quote + other.dropped_no_quote,
            dropped_low_conf=self.dropped_low_conf + other.dropped_low_conf,
        )

    def summary(self) -> str:
        return (
            f"{self.kept}/{self.proposed} kept"
            + (f", {self.relocated} relocated" if self.relocated else "")
            + (f", {self.dropped} dropped ({self.drop_rate:.0%})" if self.dropped else "")
        )


@dataclass
class Anchored:
    """A model proposal that survived, bound to real audio."""

    segment_id: int
    start_ms: int
    end_ms: int
    quote: str
    confidence: float
    speaker: str | None
    relocated: bool
    match_score: float
    payload: dict[str, Any] = field(default_factory=dict)


def _normalize(text: str) -> str:
    """Compare on words alone.

    Models routinely re-punctuate and re-case quotes while reproducing the
    words exactly. That is not hallucination and should not be punished, so
    punctuation and case are stripped before matching.
    """
    return " ".join("".join(c.lower() if c.isalnum() or c.isspace() else " "
                            for c in text).split())


def _score(quote: str, segment_text: str) -> float:
    """How well a quote matches a single segment, 0-100.

    Kept for callers that genuinely mean "within this one segment". The
    directional cap matters: `partial_ratio` slides the shorter string over
    the longer one, so a two-word segment would otherwise score a perfect 100
    against any longer quote containing those words.
    """
    q, seg = _normalize(quote), _normalize(segment_text)
    if not q or not seg:
        return 0.0
    if q in seg:
        return 100.0
    score = float(fuzz.partial_ratio(q, seg))
    if len(q) > len(seg):
        score *= len(seg) / len(q)
    return score


def _normalize_map(text: str) -> tuple[str, list[int]]:
    """Normalize, keeping the source index of every character produced.

    The map is what lets a match be reported using the transcript's own words
    instead of the model's retyping of them.
    """
    out: list[str] = []
    idx: list[int] = []
    at_space = True
    for i, ch in enumerate(text):
        if ch.isalnum():
            out.append(ch.lower())
            idx.append(i)
            at_space = False
        elif not at_space:
            out.append(" ")
            idx.append(i)
            at_space = True
    while out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


@dataclass
class _Index:
    """A chunk prepared for matching, in both normalized and original form."""

    normalized: str
    original: str
    to_original: list[int]          # normalized index -> original index
    spans: list[tuple[int, int, ChunkSegment]]

    def segment_at(self, index: int) -> ChunkSegment | None:
        for start, end, seg in self.spans:
            if start <= index < end:
                return seg
        best: ChunkSegment | None = None
        for start, _, seg in self.spans:
            if start <= index:
                best = seg
        return best or (self.spans[0][2] if self.spans else None)

    def verbatim(self, start: int, end: int) -> str:
        """The transcript's own text for a normalized span."""
        if not self.to_original or start >= len(self.to_original):
            return ""
        start = max(0, min(start, len(self.to_original) - 1))
        end = max(start + 1, min(end, len(self.to_original)))
        first = self.to_original[start]
        last = self.to_original[end - 1]
        return self.original[first:last + 1].strip()


def _index_chunk(chunk: Chunk) -> _Index:
    """Prepare a chunk for matching."""
    originals: list[str] = []
    normals: list[str] = []
    to_original: list[int] = []
    spans: list[tuple[int, int, ChunkSegment]] = []
    opos = 0
    npos = 0
    for seg in chunk.segments:
        norm, cmap = _normalize_map(seg.text)
        if not norm:
            continue
        if normals:
            originals.append(" ")
            normals.append(" ")
            to_original.append(opos)
            opos += 1
            npos += 1
        base = opos
        originals.append(seg.text)
        opos += len(seg.text)
        spans.append((npos, npos + len(norm), seg))
        normals.append(norm)
        to_original.extend(base + j for j in cmap)
        npos += len(norm)
    return _Index("".join(normals), "".join(originals), to_original, spans)


def _locate(quote: str, index: _Index) -> tuple[ChunkSegment, ChunkSegment, float, str] | None:
    """Find a quote anywhere in the chunk the model was shown.

    Matching per segment was wrong, and only real recordings revealed it. ASR
    segment boundaries fall wherever the decoder happened to stop — often mid
    clause, and on a real transcript the median segment is a fragment — so a
    quote worth reporting usually spans two or three of them. A per-segment
    gate rejected genuine verbatim evidence at around a 70% rate.

    The safety property is unchanged: the words must appear in what the model
    was actually shown. What is returned, though, is the transcript's own text
    for the matched span, not the model's retyping of it. Models quietly tidy
    disfluencies — "I don't know I I don't really" comes back with the stutter
    removed — and a quote presented as verbatim should be the recording's
    words, not a cleaned-up paraphrase that happened to score well.
    """
    q = _normalize(quote)
    if not q or not index.normalized:
        return None

    at = index.normalized.find(q)
    if at >= 0:
        start_seg = index.segment_at(at)
        end_seg = index.segment_at(at + len(q) - 1)
        if start_seg and end_seg:
            return start_seg, end_seg, 100.0, index.verbatim(at, at + len(q))
        return None

    alignment = fuzz.partial_ratio_alignment(q, index.normalized)
    if alignment is None:
        return None
    score = float(alignment.score)
    # A quote longer than everything it was shown cannot be fully present.
    if len(q) > len(index.normalized):
        score *= len(index.normalized) / len(q)
    start_seg = index.segment_at(alignment.dest_start)
    end_seg = index.segment_at(max(alignment.dest_start, alignment.dest_end - 1))
    if not start_seg or not end_seg:
        return None
    return (start_seg, end_seg, score,
            index.verbatim(alignment.dest_start, alignment.dest_end))


def anchor_items(
    items: list[dict[str, Any]],
    chunk: Chunk,
    *,
    threshold: float = 90.0,
    min_confidence: float = 0.0,
    min_quote_words: int = 2,
) -> tuple[list[Anchored], AnchorStats]:
    """Validate model proposals against the chunk they were generated from.

    `items` are dicts carrying at least `segment_id` and `quote`; any other
    keys are preserved on the result's `payload` for the caller to use.
    """
    lookup = chunk.lookup()
    index = _index_chunk(chunk)
    stats = AnchorStats(proposed=len(items))
    kept: list[Anchored] = []

    for item in items:
        quote = str(item.get("quote") or "").strip()
        if len(quote.split()) < min_quote_words:
            stats.dropped_no_quote += 1
            continue

        confidence = _as_float(item.get("confidence"), default=1.0)
        if confidence < min_confidence:
            stats.dropped_low_conf += 1
            continue

        raw_id = item.get("segment_id")
        cited = lookup.get(_as_int(raw_id)) if raw_id is not None else None

        found = _locate(quote, index)
        if found is None or found[2] < threshold or not found[3]:
            # The words are not in what the model was shown. This is the
            # fabrication case, and it is the one that must always be dropped.
            if cited is None:
                stats.dropped_no_segment += 1
            else:
                stats.dropped_no_quote += 1
            continue

        start_seg, end_seg, score, verbatim = found
        relocated = cited is None or cited.id != start_seg.id

        payload = {k: v for k, v in item.items()
                   if k not in {"segment_id", "quote", "confidence"}}
        kept.append(
            Anchored(
                segment_id=start_seg.id,
                start_ms=start_seg.start_ms,
                # End at the segment the quote finishes in, so clicking it
                # plays the whole quote rather than its first fragment.
                end_ms=max(end_seg.end_ms, start_seg.end_ms),
                # The recording's words, not the model's retyping of them.
                quote=verbatim,
                confidence=confidence,
                speaker=start_seg.speaker,
                relocated=relocated,
                match_score=score,
                payload=payload,
            )
        )
        stats.kept += 1
        if relocated:
            stats.relocated += 1

    return kept, stats


def dedupe(items: list[Anchored], *, key: str | None = None) -> list[Anchored]:
    """Collapse duplicates produced by chunk overlap.

    Two proposals are the same observation if they land on the same segment
    and — when `key` is given, e.g. a lens category — say the same thing about
    it. The higher-confidence one wins.
    """
    best: dict[tuple, Anchored] = {}
    for item in items:
        k = (item.segment_id, item.payload.get(key) if key else None)
        current = best.get(k)
        if current is None or item.confidence > current.confidence:
            best[k] = item
    return sorted(best.values(), key=lambda a: (a.start_ms, a.segment_id))


def _as_int(value: Any) -> int:
    try:
        return int(str(value).strip().strip("[]"))
    except (TypeError, ValueError):
        return -1


def _as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(f, 0.0), 1.0)
