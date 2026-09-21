"""Cross-note synthesis engine — 'Ask Your Library'.

Retrieves evidence across notes using SQLite FTS5, section summaries, and diagnostic
findings, then synthesizes a factual, evidence-backed answer citing specific notes,
speakers, and timestamps using the local Ollama LLM.
"""

from __future__ import annotations

import re
from typing import Any

from . import db
from .config import Settings


def _ms_to_ts(ms: int) -> str:
    total_seconds = max(0, ms // 1000)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def gather_evidence(conn, query: str, note_ids: list[int] | None = None, limit: int = 12) -> list[dict]:
    """Retrieve top relevant transcript segments and sections across notes."""
    terms = [w for w in re.split(r"\W+", query) if len(w) >= 3]
    if not terms:
        terms = [query.strip()] if query.strip() else []

    evidence: list[dict] = []
    seen_segments = set()

    # 1. Search via FTS5 if terms exist
    if terms:
        fts_query = " OR ".join(f'"{t}"' for t in terms[:6])
        try:
            cur = conn.execute(
                """SELECT s.id AS segment_id, s.note_id, s.start_ms, s.end_ms, s.text,
                          n.title, n.source_name,
                          COALESCE(sp.display_name, sp.label, 'Speaker') AS speaker
                     FROM segments_fts
                     JOIN segments s ON s.id = segments_fts.rowid
                     JOIN notes n ON n.id = s.note_id
                     LEFT JOIN speakers sp ON sp.id = s.speaker_id
                    WHERE segments_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?""",
                (fts_query, limit),
            )
            for r in cur.fetchall():
                if note_ids and r["note_id"] not in note_ids:
                    continue
                seg_id = r["segment_id"]
                if seg_id not in seen_segments:
                    seen_segments.add(seg_id)
                    evidence.append({
                        "note_id": r["note_id"],
                        "note_title": r["title"] or r["source_name"],
                        "start_ms": r["start_ms"],
                        "end_ms": r["end_ms"],
                        "speaker": r["speaker"],
                        "text": r["text"],
                        "type": "transcript",
                    })
        except Exception:
            pass

    # 2. Search findings quotes
    for term in terms[:4]:
        f_rows = conn.execute(
            """SELECT f.id, f.note_id, f.lens_id, f.category, f.quote, f.rationale,
                      f.start_ms, f.end_ms, n.title, n.source_name,
                      COALESCE(sp.display_name, sp.label, 'Speaker') AS speaker
                 FROM findings f
                 JOIN notes n ON n.id = f.note_id
                 LEFT JOIN speakers sp ON sp.id = f.speaker_id
                WHERE f.quote LIKE ? OR f.rationale LIKE ?
                LIMIT 4""",
            (f"%{term}%", f"%{term}%"),
        ).fetchall()
        for fr in f_rows:
            if note_ids and fr["note_id"] not in note_ids:
                continue
            evidence.append({
                "note_id": fr["note_id"],
                "note_title": fr["title"] or fr["source_name"],
                "start_ms": fr["start_ms"],
                "end_ms": fr["end_ms"],
                "speaker": fr["speaker"],
                "text": f"[{fr['lens_id']} / {fr['category']}] “{fr['quote']}” — {fr['rationale'] or ''}",
                "type": "finding",
            })

    # 3. Search note sections (summaries / action items)
    for term in terms[:3]:
        s_rows = conn.execute(
            """SELECT ns.note_id, ns.kind, ns.content_md, n.title, n.source_name
                 FROM note_sections ns
                 JOIN notes n ON n.id = ns.note_id
                WHERE ns.content_md LIKE ?
                LIMIT 3""",
            (f"%{term}%",),
        ).fetchall()
        for sr in s_rows:
            if note_ids and sr["note_id"] not in note_ids:
                continue
            evidence.append({
                "note_id": sr["note_id"],
                "note_title": sr["title"] or sr["source_name"],
                "start_ms": 0,
                "end_ms": 0,
                "speaker": "Summary",
                "text": f"[{sr['kind'].upper()}] {sr['content_md'][:280]}...",
                "type": "section",
            })

    return evidence[:limit]


def synthesize_library_query(
    conn,
    settings: Settings,
    query: str,
    note_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Synthesize cross-note answer citing verbatim evidence."""
    evidence = gather_evidence(conn, query, note_ids=note_ids, limit=14)

    if not evidence:
        return {
            "query": query,
            "answer": "No relevant discussions or findings were found matching this query in your library.",
            "citations": [],
            "evidence_count": 0,
        }

    # Build prompt context blocks
    blocks = []
    citations: list[dict] = []

    for i, ev in enumerate(evidence, 1):
        ts_str = _ms_to_ts(ev["start_ms"])
        blocks.append(
            f"EVIDENCE [{i}]: Note: '{ev['note_title']}' | Time: {ts_str} | Speaker: {ev['speaker']}\n"
            f"Content: {ev['text']}"
        )
        citations.append({
            "index": i,
            "note_id": ev["note_id"],
            "note_title": ev["note_title"],
            "start_ms": ev["start_ms"],
            "end_ms": ev["end_ms"],
            "speaker": ev["speaker"],
            "quote": ev["text"],
            "type": ev["type"],
        })

    evidence_text = "\n\n".join(blocks)

    system_prompt = (
        "You are an analytical assistant answering questions across the user's audio note library.\n"
        "Answer the user's question accurately and concisely based strictly on the provided evidence blocks.\n"
        "Cite your sources using evidence numbers in brackets, e.g. [1], [2], or by mentioning the note title.\n"
        "Never invent information not supported by the evidence."
    )

    user_prompt = (
        f"QUESTION: {query}\n\n"
        f"EVIDENCE FROM RECORDINGS:\n{evidence_text}\n\n"
        "Please provide a structured synthesis answering the question, highlighting key findings, decisions, and speakers."
    )

    answer = ""
    # Try calling local LLM via Ollama
    client = settings.llm_client()
    try:
        response = client.chat(
            settings.model_distill,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        answer = response.get("content", "").strip()
    except Exception:
        # Graceful fallback: synthesize direct extractive findings if Ollama is offline
        answer_lines = [
            f"Found {len(evidence)} relevant excerpts matching your query in your library:\n"
        ]
        for ev in evidence[:6]:
            ts_str = _ms_to_ts(ev["start_ms"])
            answer_lines.append(
                f"- **{ev['note_title']}** ({ts_str} - {ev['speaker']}): {ev['text']}"
            )
        answer = "\n".join(answer_lines)

    return {
        "query": query,
        "answer": answer,
        "citations": citations,
        "evidence_count": len(evidence),
    }
