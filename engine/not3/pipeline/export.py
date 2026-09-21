"""Stage 8 — markdown export.

Plain `.md` with YAML frontmatter, which is the one idea worth taking wholesale
from Detto: the durable artefact is a text file the user owns and can open in
Obsidian, grep, or sync however they like. The database is an index over these,
not a place data gets trapped.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

DISCLAIMER = (
    "Pattern observations below are produced by a language model reading the "
    "transcript. Each is tied to a verbatim quote and a timestamp so it can be "
    "checked against the recording. They are descriptive observations, not a "
    "clinical or diagnostic assessment."
)

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(title: str, fallback: str = "note") -> str:
    name = _UNSAFE.sub("", title or "").strip().strip(".")
    name = re.sub(r"\s+", " ", name)[:80]
    return name or fallback


def _ts(ms: int) -> str:
    s = int(ms) // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _yaml_scalar(value) -> str:
    if value is None:
        return '""'
    text = str(value)
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return text
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _frontmatter(note: sqlite3.Row, topics: list[str], counts: dict[str, int]) -> str:
    lines = ["---"]
    lines.append(f"title: {_yaml_scalar(note['title'] or note['source_name'])}")
    lines.append(f"source: {_yaml_scalar(note['source_name'])}")
    lines.append(f"created: {_yaml_scalar(note['created_at'])}")
    lines.append(f"duration: {_yaml_scalar(_ts(note['duration_ms']))}")
    if note["language"]:
        lines.append(f"language: {_yaml_scalar(note['language'])}")
    asr = f"{note['asr_model']} ({note['asr_backend']})"
    lines.append(f"asr: {_yaml_scalar(asr)}")
    for key, value in counts.items():
        lines.append(f"{key}: {value}")
    if topics:
        lines.append("tags:")
        lines.extend(f"  - {_yaml_scalar(t)}" for t in topics)
    lines.append("---")
    return "\n".join(lines)


def render(
    note: sqlite3.Row,
    segments: list[sqlite3.Row],
    sections: dict[str, str],
    highlights: list[sqlite3.Row],
    findings: list[sqlite3.Row],
    *,
    lens_names: dict[str, str] | None = None,
    include_transcript: bool = True,
) -> str:
    lens_names = lens_names or {}
    topics = [t.strip() for t in (sections.get("topics") or "").split(",") if t.strip()]
    counts = {
        "segments": len(segments),
        "highlights": len(highlights),
        "findings": len(findings),
    }

    out: list[str] = [_frontmatter(note, topics, counts), ""]
    out.append(f"# {note['title'] or note['source_name']}")
    out.append("")

    if summary := sections.get("summary"):
        out += ["## Summary", "", summary, ""]

    if key_points := sections.get("key_points"):
        out += ["## Key points", "", key_points, ""]

    if action_items := sections.get("action_items"):
        out += ["## Action items", "", action_items, ""]

    if highlights:
        out += ["## Highlights", ""]
        for h in highlights:
            out.append(f"- **[{_ts(h['start_ms'])}]** “{h['quote'].strip()}”")
            if h["reason"]:
                out.append(f"  - {h['reason']}")
        out.append("")

    if findings:
        out += ["## Patterns", "", f"> {DISCLAIMER}", ""]
        by_lens: dict[str, list[sqlite3.Row]] = {}
        for f in findings:
            by_lens.setdefault(f["lens_id"], []).append(f)
        for lens_id, items in by_lens.items():
            out.append(f"### {lens_names.get(lens_id, lens_id)}")
            out.append("")
            for f in items:
                label = str(f["category"]).replace("_", " ")
                out.append(
                    f"- **[{_ts(f['start_ms'])}]** *{label}* "
                    f"({f['confidence']:.0%}) — “{f['quote'].strip()}”"
                )
                if f["rationale"]:
                    out.append(f"  - {f['rationale']}")
            out.append("")

    if include_transcript and segments:
        out += ["## Transcript", ""]
        current_speaker = object()
        for s in segments:
            speaker = s["speaker_name"] or s["speaker_label"]
            if speaker and speaker != current_speaker:
                out.append(f"**{speaker}**")
                current_speaker = speaker
            out.append(f"`[{_ts(s['start_ms'])}]` {s['text'].strip()}")
            out.append("")

    return "\n".join(out).rstrip() + "\n"


def write(
    conn: sqlite3.Connection,
    note_id: int,
    dest_dir: Path,
    *,
    include_transcript: bool = True,
) -> Path:
    from .. import db

    note = db.get_note(conn, note_id)
    if note is None:
        raise ValueError(f"no note {note_id}")

    lens_names = {
        r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM lenses").fetchall()
    }
    content = render(
        note,
        db.get_segments(conn, note_id),
        db.get_sections(conn, note_id),
        db.get_highlights(conn, note_id),
        db.get_findings(conn, note_id),
        lens_names=lens_names,
        include_transcript=include_transcript,
    )

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{safe_filename(note['title'] or note['source_name'])}.md"
    path.write_text(content, encoding="utf-8")
    return path
