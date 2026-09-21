"""Stage 6 — the lens engine.

A lens is a YAML file describing a way of reading a transcript: a set of
categories, each with a definition and examples, plus thresholds. The engine
turns it into a JSON schema and a prompt, runs it chunk by chunk, and puts
every proposal through the anchoring gate.

Adding a lens means adding a file. No code, no rebuild, no restart. A user
lens whose `id` matches a built-in shadows it, so the shipped ones can be
edited without being lost on upgrade.

All lenses emit the same shape — a quote, a category, a confidence and a
rationale — including the emotional one, where the categories are affective
states. Keeping one shape means one anchoring path, one storage table and one
way to render findings against the timeline.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from typing import TYPE_CHECKING

from ..config import Settings
from ..llm.anchor import Anchored, AnchorStats, anchor_items, dedupe
from ..llm.chunker import Chunk, ChunkSegment, chunk_segments

if TYPE_CHECKING:
    from ..llm.ollama import Client

SYSTEM = (
    "You identify specific, evidence-backed patterns in transcripts of real "
    "conversations. You quote verbatim and never paraphrase inside a quote. "
    "You describe what was said; you do not diagnose, label people, or "
    "speculate about anything not present in the text. Returning nothing is "
    "always acceptable and is better than a weak match."
)


class LensError(RuntimeError):
    pass


@dataclass
class Category:
    id: str
    label: str
    definition: str
    positive_example: str = ""
    negative_example: str = ""


@dataclass
class Lens:
    id: str
    name: str
    version: int
    description: str = ""
    categories: list[Category] = field(default_factory=list)
    guidance: str = ""
    disclaimer: str = ""
    temperature: float = 0.2
    min_confidence: float = 0.6
    max_per_chunk: int = 5
    requires_speakers: bool = False
    path: Path | None = None

    @property
    def category_ids(self) -> list[str]:
        return [c.id for c in self.categories]

    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "segment_id": {"type": "integer"},
                            "quote": {"type": "string"},
                            "category": {"type": "string", "enum": self.category_ids},
                            # A model that has considered a line and rejected it
                            # needs somewhere to say so. Without this field the
                            # only way to express "close, but no" is silence,
                            # and models reliably emit the finding instead —
                            # complete with a rationale explaining why it does
                            # not qualify. Giving rejection a channel removes
                            # the pressure to produce a false positive.
                            "verdict": {"type": "string",
                                        "enum": ["instance", "near_miss"]},
                            "confidence": {"type": "number"},
                            "rationale": {"type": "string"},
                        },
                        "required": ["segment_id", "quote", "category", "verdict",
                                     "confidence", "rationale"],
                    },
                }
            },
            "required": ["findings"],
        }

    def render_categories(self) -> str:
        blocks = []
        for c in self.categories:
            block = [f"- {c.id} ({c.label}): {c.definition}"]
            if c.positive_example:
                block.append(f"    counts:         “{c.positive_example}”")
            if c.negative_example:
                block.append(f"    does not count: “{c.negative_example}”")
            blocks.append("\n".join(block))
        return "\n".join(blocks)

    def prompt(self, chunk: Chunk) -> str:
        parts = [
            "Below is part of a transcript. Each line is:",
            "",
            "[segment_id] (timestamp) optional speaker: text",
            "",
            f"Identify at most {self.max_per_chunk} instances of the following "
            "patterns. Each category lists what counts and, where given, a "
            "near-miss that does NOT count — respect that distinction, it is "
            "the difference between a useful result and noise.",
            "",
            self.render_categories(),
            "",
        ]
        if self.guidance:
            parts += [self.guidance.strip(), ""]
        parts += [
            "For each: `segment_id` is the line, `quote` is copied "
            "**verbatim** from that line, `category` is one of the ids above, "
            "`confidence` is 0 to 1, and `rationale` is one short clause "
            "explaining what in the quote makes it that category.",
            "",
            "`verdict` is either `instance` or `near_miss`. Use `near_miss` "
            "for a line that resembles a category but does not actually "
            "qualify — it retracts an earlier statement, it matches a "
            "'does not count' example, or it is merely on a difficult "
            "subject. Only `instance` is recorded; `near_miss` is how you "
            "say you considered a line and ruled it out. If your rationale "
            "would explain why something does NOT qualify, the verdict is "
            "`near_miss`.",
            "",
            "Only flag clear instances. Do not flag a line merely because it "
            "is negative, emotional, or on a difficult subject. If this part "
            "contains no clear instance, return an empty list.",
            "",
            "TRANSCRIPT",
            chunk.render(),
        ]
        return "\n".join(parts)


def _as_str(value: Any, default: str = "") -> str:
    return str(value).strip() if value is not None else default


def parse_lens(data: dict, path: Path | None = None) -> Lens:
    if not isinstance(data, dict):
        raise LensError(f"{path}: lens file must be a YAML mapping")
    for required in ("id", "name", "categories"):
        if not data.get(required):
            raise LensError(f"{path}: lens is missing required field '{required}'")

    categories: list[Category] = []
    for raw in data["categories"]:
        if not isinstance(raw, dict) or not raw.get("id"):
            raise LensError(f"{path}: every category needs an 'id'")
        categories.append(
            Category(
                id=_as_str(raw["id"]),
                label=_as_str(raw.get("label"), _as_str(raw["id"]).replace("_", " ")),
                definition=_as_str(raw.get("definition")),
                positive_example=_as_str(raw.get("positive_example")),
                negative_example=_as_str(raw.get("negative_example")),
            )
        )

    model = data.get("model") or {}
    thresholds = data.get("thresholds") or {}
    return Lens(
        id=_as_str(data["id"]),
        name=_as_str(data["name"]),
        version=int(data.get("version", 1)),
        description=_as_str(data.get("description")),
        categories=categories,
        guidance=_as_str(data.get("guidance")),
        disclaimer=_as_str(data.get("disclaimer")),
        temperature=float(model.get("temperature", 0.2)),
        min_confidence=float(thresholds.get("min_confidence", 0.6)),
        max_per_chunk=int(thresholds.get("max_per_chunk", 5)),
        requires_speakers=bool(data.get("requires_speakers", False)),
        path=path,
    )


def load_lens(path: Path) -> Lens:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LensError(f"{path.name}: invalid YAML — {exc}") from exc
    return parse_lens(data, path)


def load_lenses(settings: Settings) -> list[Lens]:
    """Built-in lenses, then user lenses, with user ids shadowing built-ins."""
    lenses: dict[str, Lens] = {}
    for directory in (settings.lenses_dir, settings.user_lenses_dir):
        if not Path(directory).is_dir():
            continue
        for path in sorted(Path(directory).glob("*.y*ml")):
            try:
                lens = load_lens(path)
            except LensError:
                # A malformed user lens must not take down every other lens.
                continue
            lenses[lens.id] = lens
    return sorted(lenses.values(), key=lambda l: l.name)


def validate_lens_yaml(yaml_str: str) -> tuple[bool, str, Lens | None]:
    """Validate raw YAML string without writing it to disk."""
    try:
        data = yaml.safe_load(yaml_str)
    except yaml.YAMLError as exc:
        return False, f"Invalid YAML: {exc}", None
    if not isinstance(data, dict):
        return False, "Lens YAML must be a dictionary/mapping", None
    try:
        lens = parse_lens(data)
        if not lens.categories:
            return False, "Lens must define at least one category", None
        return True, "", lens
    except LensError as exc:
        return False, str(exc), None


def save_user_lens(settings: Settings, yaml_str: str) -> Lens:
    """Validate and write a user lens into settings.user_lenses_dir."""
    valid, err, lens = validate_lens_yaml(yaml_str)
    if not valid or lens is None:
        raise LensError(err)
    settings.user_lenses_dir.mkdir(parents=True, exist_ok=True)
    target_path = settings.user_lenses_dir / f"{lens.id}.yaml"
    target_path.write_text(yaml_str, encoding="utf-8")
    lens.path = target_path
    return lens


def delete_user_lens(settings: Settings, lens_id: str) -> bool:
    """Delete a user lens file if present in settings.user_lenses_dir."""
    target_path = settings.user_lenses_dir / f"{lens_id}.yaml"
    if target_path.is_file():
        target_path.unlink()
        return True
    # Also check .yml
    alt_path = settings.user_lenses_dir / f"{lens_id}.yml"
    if alt_path.is_file():
        alt_path.unlink()
        return True
    return False


def sync_registry(conn, settings: Settings) -> list[Lens]:
    """Reflect the lens files on disk into the database, preserving enablement."""
    from .. import db

    lenses = load_lenses(settings)
    active_ids = {l.id for l in lenses}
    now = db.utcnow()
    with db.tx(conn):
        # Remove any database lens rows whose files no longer exist on disk
        existing = [r["id"] for r in conn.execute("SELECT id FROM lenses").fetchall()]
        for eid in existing:
            if eid not in active_ids:
                conn.execute("DELETE FROM lenses WHERE id = ?", (eid,))

        for lens in lenses:
            conn.execute(
                """INSERT INTO lenses (id, name, version, description, path,
                                       enabled, disclaimer, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                   ON CONFLICT (id) DO UPDATE SET
                     name = excluded.name, version = excluded.version,
                     description = excluded.description, path = excluded.path,
                     disclaimer = excluded.disclaimer, updated_at = excluded.updated_at""",
                (lens.id, lens.name, lens.version, lens.description,
                 str(lens.path or ""), lens.disclaimer, now),
            )
    return lenses


@dataclass
class LensResult:
    lens: Lens
    findings: list[Anchored] = field(default_factory=list)
    stats: AnchorStats = field(default_factory=AnchorStats)
    model: str = ""
    duration_ms: int = 0
    near_misses: int = 0
    """Lines the model considered and ruled out. A healthy lens has some:
    zero usually means it is not discriminating, only matching."""


def run_lens(
    lens: Lens,
    segments: Sequence[ChunkSegment],
    settings: Settings,
    client: Client | None = None,
    *,
    on_progress: Callable[[float, str], None] | None = None,
) -> LensResult:
    client = client or settings.llm_client()
    model = settings.model_lens
    started = time.perf_counter()

    chunks = chunk_segments(
        segments,
        max_tokens=settings.chunk_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
    )
    if not chunks:
        return LensResult(lens=lens, model=model)

    valid = set(lens.category_ids)
    found: list[Anchored] = []
    stats = AnchorStats()
    near_misses = 0

    for chunk in chunks:
        if on_progress:
            on_progress(chunk.index / len(chunks),
                        f"{lens.name}: part {chunk.index + 1}/{len(chunks)}")
        data = client.structured(
            model,
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": lens.prompt(chunk)},
            ],
            lens.schema(),
            temperature=lens.temperature,
        )

        proposals = list(data.get("findings") or [])
        rejected = [p for p in proposals
                    if str(p.get("verdict", "instance")).strip() == "near_miss"]
        near_misses += len(rejected)
        items = [
            item for item in proposals
            if str(item.get("verdict", "instance")).strip() == "instance"
            # The schema constrains the enum, but a model can still emit a
            # category it invented; those are dropped before anchoring so they
            # never reach a column that assumes a known category.
            and str(item.get("category", "")).strip() in valid
        ]
        kept, chunk_stats = anchor_items(
            items, chunk,
            threshold=settings.quote_match_threshold,
            min_confidence=lens.min_confidence,
        )
        found.extend(kept)
        stats = stats.merge(chunk_stats)

    if on_progress:
        on_progress(1.0, f"{lens.name}: done")

    return LensResult(
        lens=lens,
        findings=dedupe(found, key="category"),
        stats=stats,
        near_misses=near_misses,
        model=model,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
