"""Sample library generation and Library JSON Import/Export.

Provides a rich, realistic, multi-speaker sample library with 3 distinct sessions:
1. Q3 Architecture & Security Alignment (Multi-speaker: Dr. Vance, Alex, Elena)
2. Clinical Operations & Discovery (Multi-speaker: Marcus, Claire)
3. Engineering Leadership & Mentorship (Multi-speaker: Maya, Liam)

Each session is populated with millisecond-timed segments, FTS5 text indexing,
speaker diarization attributions, distilled note sections (summary, key_points,
action_items, topics), and verbatim-anchored diagnostic lens findings.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from . import db
from .config import Settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SAMPLE_SESSIONS = [
    {
        "hash": "not3_sample_session_001",
        "title": "Q3 Architecture & Security Alignment",
        "source_name": "q3_architecture_security.wav",
        "duration_ms": 142000,
        "speakers": [
            ("SPEAKER_00", "Dr. Vance (Security Officer)"),
            ("SPEAKER_01", "Alex (Lead Architect)"),
            ("SPEAKER_02", "Elena (VP of Product)"),
        ],
        "segments": [
            (0, 0, 8500, "Alex", "Good morning everyone. Let's align on the Q3 engine architecture and privacy constraints."),
            (1, 8600, 19200, "Dr. Vance", "From the security and compliance side, our position is strict: zero cloud sync. Complete offline processing eliminates the entire class of cloud data breach risks."),
            (2, 19300, 31000, "Elena", "If we disable cloud sync entirely our enterprise customers will abandon us completely. They expect multi-device synchronization."),
            (3, 31200, 42500, "Alex", "Not if we use local-first SQLite with sync-on-demand or peer-to-peer transport. Nothing leaves the machine. Transcription is whisper.cpp; the language work is Ollama. Both run locally."),
            (4, 42800, 56000, "Dr. Vance", "That satisfies our HIPAA and GDPR requirements. But how does whisper.cpp perform on our target hardware?"),
            (5, 56200, 71500, "Alex", "On the RTX 5070 Blackwell test bench with large-v3-turbo, we achieved an RTF of 0.029, which processes a 60-minute audio file in under 1.7 minutes."),
            (6, 71800, 84200, "Elena", "If latency is the blocker for my team and security is Dr. Vance's priority, local edge models satisfy both constraints nicely."),
            (7, 84500, 97000, "Alex", "Exactly. The invariant is that every highlight and finding references a real segment and a real time range, so anything the app claims can be clicked and played back."),
            (8, 97300, 111000, "Dr. Vance", "I will complete the security isolation audit of whisper.cpp and ONNX runtimes by Friday."),
            (9, 111200, 124500, "Alex", "And I will finalize the SQLite encryption specification and database schema before Thursday's code freeze."),
            (10, 124800, 141500, "Elena", "Excellent. I will present the offline-first privacy roadmap to the executive committee next Tuesday."),
        ],
        "sections": {
            "summary": "Technical deliberation on migrating from cloud ASR to 100% offline edge processing. The team aligned on whisper.cpp with CUDA/Metal acceleration, zero cloud sync for medical and enterprise transcripts, and local SQLite with verbatim quote anchoring.",
            "key_points": "- Complete offline processing satisfies strict HIPAA and EU GDPR compliance mandates.\n- Blackwell sm_120 CUDA speedup achieved 0.029x RTF (1.7 minutes for 60-minute audio).\n- SQLite in WAL mode with Foreign Keys guarantees that every finding links to verbatim audio timestamps.\n- Cloud sync is officially eliminated from the Q3 roadmap in favor of local privacy-preserving architecture.",
            "action_items": "- Dr. Vance: Complete security isolation audit of whisper.cpp and ONNX runtimes by Friday.\n- Alex: Finalize SQLite encryption specification and database schema before Thursday's code freeze.\n- Elena: Present the offline-first privacy roadmap to the executive committee next Tuesday.",
            "topics": "Architecture, Privacy & Compliance, Local LLM, GPU Acceleration, Offline Storage",
        },
        "highlights": [
            (3, 31200, 42500, "Nothing leaves the machine. Transcription is whisper.cpp; the language work is Ollama. Both run locally.", "Core architectural design principle"),
            (1, 8600, 19200, "Complete offline processing eliminates the entire class of cloud data breach risks.", "Regulatory and security justification"),
        ],
        "findings": [
            ("cognitive_distortions", 1, "catastrophizing", "If we disable cloud sync entirely our enterprise customers will abandon us completely.", 2, 19300, 31000, "Elena", 0.88, "Frames customer churn in absolute catastrophic terms without empirical validation"),
            ("strategic_alignment", 1, "firm_commitment", "I will complete the security isolation audit of whisper.cpp and ONNX runtimes by Friday.", 8, 97300, 111000, "Dr. Vance", 0.94, "Unequivocal deliverable ownership with fixed calendar deadline"),
            ("strategic_alignment", 1, "constructive_synthesis", "If latency is the blocker for my team and security is Dr. Vance's priority, local edge models satisfy both constraints nicely.", 6, 71800, 84200, "Elena", 0.91, "Bridges latency and security constraints into a coherent compromise"),
            ("communication_patterns", 1, "constructive_synthesis", "Not if we use local-first SQLite with sync-on-demand or peer-to-peer transport.", 3, 31200, 42500, "Alex", 0.87, "Constructive alternative offered in response to objection"),
        ],
    },
    {
        "hash": "not3_sample_session_002",
        "title": "Clinical Operations & Discovery Interview",
        "source_name": "clinical_operations_discovery.wav",
        "duration_ms": 118000,
        "speakers": [
            ("SPEAKER_00", "Marcus (Enterprise Solutions)"),
            ("SPEAKER_01", "Claire (VP of Clinical Operations)"),
        ],
        "segments": [
            (0, 0, 11000, "Marcus", "Thanks for joining, Claire. We want to understand where clinicians are losing the most time during consultation documentation."),
            (1, 11200, 25500, "Claire", "We desperately need to eliminate the four-hour charting backlog every single evening. Physicians are burning out because EHR systems require endless manual typing."),
            (2, 25800, 38000, "Marcus", "If transcription could run locally right in the examination room with zero cloud transfer, how would your compliance team respond?"),
            (3, 38200, 52000, "Claire", "Local processing is our holy grail. If audio never leaves the room, hospital legal approval takes two weeks instead of twelve months."),
            (4, 52200, 66000, "Claire", "However, we cannot accept hallucinations. Every single summarized finding must trace back to the patient's exact words."),
            (5, 66200, 80000, "Marcus", "That is exactly how Not3 works. We use a fuzzy anchoring gate that rejects any quote that does not verbatim match the transcript."),
            (6, 80200, 93000, "Claire", "I will assemble a pilot cohort of five senior clinicians for the trial by next Wednesday."),
            (7, 93200, 106000, "Marcus", "I will prepare the medical terminology benchmark report and deliver workstation installers by Monday."),
            (8, 106200, 117500, "Claire", "That sounds like a partnership that will actually make a difference for our staff."),
        ],
        "sections": {
            "summary": "In-depth discovery session exploring clinical workflow bottlenecks. Claire detailed the severe administrative burden of 4-hour evening charting backlogs. Both parties aligned on local-only speech recognition and verified quote anchoring as key enablers for rapid hospital deployment.",
            "key_points": "- Clinicians spend up to 4 hours per evening on manual charting and EHR documentation.\n- Zero cloud data transfer bypasses complex 12-month compliance reviews and enables 2-week approval.\n- Verbatim quote anchoring prevents hallucinated medical summaries.\n- 5-clinician pilot cohort scheduled for initial operational trial.",
            "action_items": "- Marcus: Deliver medical terminology benchmark report and workstation installers by Monday.\n- Claire: Assemble a pilot cohort of five senior clinicians for the trial by next Wednesday.",
            "topics": "Healthcare, Clinical Documentation, Clinician Burnout, EHR, Verbatim Verification",
        },
        "highlights": [
            (1, 11200, 25500, "We desperately need to eliminate the four-hour charting backlog every single evening.", "Primary operational pain point"),
            (3, 38200, 52000, "If audio never leaves the room, hospital legal approval takes two weeks instead of twelve months.", "Key market adoption driver"),
        ],
        "findings": [
            ("readiness_for_change", 1, "change_talk", "We desperately need to eliminate the four-hour charting backlog every single evening.", 1, 11200, 25500, "Claire", 0.93, "High urgency and clear desire to change current operational model"),
            ("strategic_alignment", 1, "firm_commitment", "I will assemble a pilot cohort of five senior clinicians for the trial by next Wednesday.", 6, 80200, 93000, "Claire", 0.95, "Explicit cohort size and calendar commitment"),
            ("strategic_alignment", 1, "firm_commitment", "I will prepare the medical terminology benchmark report and deliver workstation installers by Monday.", 7, 93200, 106000, "Marcus", 0.92, "Deliverable timeline committed"),
        ],
    },
    {
        "hash": "not3_sample_session_003",
        "title": "Engineering Leadership & Mentorship 1-on-1",
        "source_name": "engineering_mentorship_1on1.wav",
        "duration_ms": 105000,
        "speakers": [
            ("SPEAKER_00", "Maya (Staff Engineering Lead)"),
            ("SPEAKER_01", "Liam (Senior Systems Engineer)"),
        ],
        "segments": [
            (0, 0, 9500, "Maya", "Hey Liam, great to connect. Let's review the diarization optimization work and your goals for Q4."),
            (1, 9800, 23500, "Liam", "If the speaker diarization has even a two-second latency then the whole real-time experience is completely ruined."),
            (2, 23800, 37000, "Maya", "So what I hear you saying is that the cognitive load of context-switching is harder than the technical implementation itself."),
            (3, 37200, 51000, "Liam", "Yes, exactly. When I am deep in ONNX Runtime C++ bindings and someone asks for an ad-hoc dashboard, I lose half a day."),
            (4, 51200, 66000, "Maya", "That is completely understandable. We can shield your deep work blocks on Tuesday and Thursday mornings so you can stay in flow."),
            (5, 66200, 80500, "Liam", "That would help immensely. I will benchmark batched Sherpa-ONNX speaker embeddings on Windows and macOS by Thursday."),
            (6, 80800, 93000, "Maya", "And I will set up bi-weekly architecture pairing sessions for the new engineers so you don't carry the mentoring load alone."),
            (7, 93200, 104500, "Liam", "I will also document the quote anchoring fuzzy matching algorithm for the team wiki."),
        ],
        "sections": {
            "summary": "1-on-1 leadership check-in between Maya and Liam. Liam raised challenges with context-switching and perfectionism around diarization latency. Maya established protected deep-work blocks and shared onboarding responsibilities.",
            "key_points": "- Liam felt context-switching disrupted deep systems engineering on ONNX Runtime.\n- Maya introduced protected focus blocks on Tuesday and Thursday mornings.\n- Liam committed to Sherpa-ONNX batching benchmarks and fuzzy matching wiki docs.\n- Shared mentoring approach adopted to prevent individual burnout.",
            "action_items": "- Liam: Benchmark batched Sherpa-ONNX speaker embeddings on Windows and macOS by Thursday.\n- Maya: Set up bi-weekly architecture pairing sessions for new engineer onboarding.\n- Liam: Document the quote anchoring fuzzy matching algorithm for the team wiki.",
            "topics": "Engineering Culture, Deep Work, Mentorship, ONNX Optimization, Team Scaling",
        },
        "highlights": [
            (2, 23800, 37000, "So what I hear you saying is that the cognitive load of context-switching is harder than the technical implementation itself.", "Exemplary active listening and validation"),
            (4, 51200, 66000, "We can shield your deep work blocks on Tuesday and Thursday mornings so you can stay in flow.", "Concrete leadership intervention"),
        ],
        "findings": [
            ("cognitive_distortions", 1, "all_or_nothing", "If the speaker diarization has even a two-second latency then the whole real-time experience is completely ruined.", 1, 9800, 23500, "Liam", 0.90, "All-or-nothing threshold applied to performance without intermediate acceptability"),
            ("empathy_active_listening", 1, "reflective_listening", "So what I hear you saying is that the cognitive load of context-switching is harder than the technical implementation itself.", 2, 23800, 37000, "Maya", 0.94, "Reflects emotional and cognitive state accurately"),
            ("strategic_alignment", 1, "firm_commitment", "I will benchmark batched Sherpa-ONNX speaker embeddings on Windows and macOS by Thursday.", 5, 66200, 80500, "Liam", 0.93, "Actionable benchmark commitment with delivery date"),
            ("strategic_alignment", 1, "firm_commitment", "I will set up bi-weekly architecture pairing sessions for the new engineers so you don't carry the mentoring load alone.", 6, 80800, 93000, "Maya", 0.91, "Leadership commitment to relieve workload"),
        ],
    },
]


def seed_sample_library(conn, settings: Settings) -> list[dict]:
    """Seed the reference sample library if not already present."""
    seeded_notes = []
    now = _now()

    for session in SAMPLE_SESSIONS:
        existing = db.find_note_by_hash(conn, session["hash"])
        if existing:
            seeded_notes.append(dict(existing))
            continue

        with db.tx(conn):
            cur = conn.execute(
                """INSERT INTO notes
                     (title, source_path, source_name, source_hash, media_path,
                      duration_ms, status, asr_backend, asr_model, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'ready', 'cuda', 'large-v3-turbo', ?, ?)""",
                (
                    session["title"],
                    f"samples/{session['source_name']}",
                    session["source_name"],
                    session["hash"],
                    "",
                    session["duration_ms"],
                    now,
                    now,
                ),
            )
            note_id = int(cur.lastrowid)

            # Insert speakers
            speaker_map: dict[str, int] = {}
            for label, display_name in session["speakers"]:
                scur = conn.execute(
                    """INSERT INTO speakers (note_id, label, display_name)
                       VALUES (?, ?, ?)""",
                    (note_id, label, display_name),
                )
                speaker_map[label] = int(scur.lastrowid)
                speaker_map[display_name.split()[0]] = int(scur.lastrowid)

            # Insert segments and index into FTS5
            seg_map: dict[int, int] = {}
            for idx, start_ms, end_ms, spk_tag, text in session["segments"]:
                spk_id = speaker_map.get(spk_tag)
                cur_seg = conn.execute(
                    """INSERT INTO segments
                         (note_id, idx, start_ms, end_ms, text, speaker_id, confidence)
                       VALUES (?, ?, ?, ?, ?, ?, 0.98)""",
                    (note_id, idx, start_ms, end_ms, text, spk_id),
                )
                real_seg_id = int(cur_seg.lastrowid)
                seg_map[idx] = real_seg_id

            # Insert sections
            for kind, content in session["sections"].items():
                conn.execute(
                    """INSERT INTO note_sections (note_id, kind, content_md, model, created_at)
                       VALUES (?, ?, ?, 'qwen3.5:9b', ?)""",
                    (note_id, kind, content, now),
                )

            # Insert highlights
            for idx, start_ms, end_ms, quote, reason in session["highlights"]:
                real_seg_id = seg_map.get(idx, 0)
                conn.execute(
                    """INSERT INTO highlights
                         (note_id, segment_id, start_ms, end_ms, quote, kind, reason, importance, model, created_at)
                       VALUES (?, ?, ?, ?, ?, 'auto', ?, 0.95, 'qwen3.5:9b', ?)""",
                    (note_id, real_seg_id, start_ms, end_ms, quote, reason, now),
                )

            # Insert findings
            for (
                lens_id,
                lens_ver,
                cat,
                quote,
                idx,
                start_ms,
                end_ms,
                spk_tag,
                conf,
                rationale,
            ) in session["findings"]:
                real_seg_id = seg_map.get(idx, 0)
                spk_id = speaker_map.get(spk_tag)
                conn.execute(
                    """INSERT INTO findings
                         (note_id, lens_id, lens_version, category, quote, segment_id,
                          start_ms, end_ms, speaker_id, confidence, rationale, model, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'qwen3.5:9b', ?)""",
                    (
                        note_id,
                        lens_id,
                        lens_ver,
                        cat,
                        quote,
                        real_seg_id,
                        start_ms,
                        end_ms,
                        spk_id,
                        conf,
                        rationale,
                        now,
                    ),
                )

        note_row = db.get_note(conn, note_id)
        if note_row:
            seeded_notes.append(dict(note_row))

    return seeded_notes


def export_library_json(conn) -> dict[str, Any]:
    """Export the entire library (notes, speakers, segments, sections, highlights, findings)."""
    notes = [dict(r) for r in conn.execute("SELECT * FROM notes ORDER BY id").fetchall()]
    speakers = [dict(r) for r in conn.execute("SELECT * FROM speakers ORDER BY id").fetchall()]
    segments = [dict(r) for r in conn.execute("SELECT * FROM segments ORDER BY id").fetchall()]
    sections = [dict(r) for r in conn.execute("SELECT * FROM note_sections ORDER BY id").fetchall()]
    highlights = [dict(r) for r in conn.execute("SELECT * FROM highlights ORDER BY id").fetchall()]
    findings = [dict(r) for r in conn.execute("SELECT * FROM findings ORDER BY id").fetchall()]

    return {
        "format": "not3_library",
        "version": 1,
        "exported_at": _now(),
        "notes": notes,
        "speakers": speakers,
        "segments": segments,
        "sections": sections,
        "highlights": highlights,
        "findings": findings,
    }


def import_library_json(conn, data: dict[str, Any]) -> dict[str, int]:
    """Import library payload, restoring notes, speakers, segments, sections, and findings."""
    if not isinstance(data, dict) or data.get("format") != "not3_library":
        raise ValueError("Invalid library package format. Expected 'not3_library'.")

    now = _now()
    imported_notes = 0
    imported_segments = 0
    imported_findings = 0

    notes_in = data.get("notes") or []
    speakers_in = data.get("speakers") or []
    segments_in = data.get("segments") or []
    sections_in = data.get("sections") or []
    highlights_in = data.get("highlights") or []
    findings_in = data.get("findings") or []

    # Map old ids to new ids to handle auto-increment safely
    note_id_map: dict[int, int] = {}
    speaker_id_map: dict[int, int] = {}
    segment_id_map: dict[int, int] = {}

    with db.tx(conn):
        for n in notes_in:
            old_id = n["id"]
            existing = db.find_note_by_hash(conn, n["source_hash"])
            if existing:
                note_id_map[old_id] = existing["id"]
                continue

            cur = conn.execute(
                """INSERT INTO notes
                     (title, source_path, source_name, source_hash, media_path,
                      duration_ms, language, status, asr_backend, asr_model,
                      error, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    n.get("title", ""),
                    n.get("source_path", ""),
                    n.get("source_name", ""),
                    n.get("source_hash", ""),
                    n.get("media_path"),
                    n.get("duration_ms", 0),
                    n.get("language"),
                    n.get("status", "ready"),
                    n.get("asr_backend"),
                    n.get("asr_model"),
                    n.get("error"),
                    n.get("created_at", now),
                    now,
                ),
            )
            new_note_id = int(cur.lastrowid)
            note_id_map[old_id] = new_note_id
            imported_notes += 1

        for spk in speakers_in:
            old_note_id = spk["note_id"]
            new_note_id = note_id_map.get(old_note_id)
            if not new_note_id:
                continue
            conn.execute(
                """INSERT INTO speakers (note_id, label, display_name)
                   VALUES (?, ?, ?)
                   ON CONFLICT (note_id, label) DO UPDATE SET display_name = excluded.display_name""",
                (new_note_id, spk["label"], spk.get("display_name")),
            )
            row = conn.execute(
                "SELECT id FROM speakers WHERE note_id = ? AND label = ?",
                (new_note_id, spk["label"]),
            ).fetchone()
            if row:
                speaker_id_map[spk["id"]] = int(row[0])

        for seg in segments_in:
            old_note_id = seg["note_id"]
            new_note_id = note_id_map.get(old_note_id)
            if not new_note_id:
                continue
            old_spk_id = seg.get("speaker_id")
            new_spk_id = speaker_id_map.get(old_spk_id) if old_spk_id else None

            conn.execute(
                """INSERT INTO segments
                     (note_id, idx, start_ms, end_ms, text, speaker_id, confidence, words_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (note_id, idx) DO UPDATE SET text = excluded.text,
                     speaker_id = excluded.speaker_id""",
                (
                    new_note_id,
                    seg["idx"],
                    seg["start_ms"],
                    seg["end_ms"],
                    seg["text"],
                    new_spk_id,
                    seg.get("confidence"),
                    seg.get("words_json"),
                ),
            )
            row = conn.execute(
                "SELECT id FROM segments WHERE note_id = ? AND idx = ?",
                (new_note_id, seg["idx"]),
            ).fetchone()
            if row:
                segment_id_map[seg["id"]] = int(row[0])
            imported_segments += 1

        for sec in sections_in:
            old_note_id = sec["note_id"]
            new_note_id = note_id_map.get(old_note_id)
            if not new_note_id:
                continue
            conn.execute(
                """INSERT INTO note_sections (note_id, kind, content_md, model, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (note_id, kind) DO UPDATE SET content_md = excluded.content_md""",
                (new_note_id, sec["kind"], sec["content_md"], sec.get("model"), now),
            )

        # Clear existing highlights & findings for the targeted notes to avoid foreign key duplicates
        for new_nid in set(note_id_map.values()):
            conn.execute("DELETE FROM highlights WHERE note_id = ?", (new_nid,))
            conn.execute("DELETE FROM findings WHERE note_id = ?", (new_nid,))

        for hl in highlights_in:
            new_note_id = note_id_map.get(hl["note_id"])
            new_seg_id = segment_id_map.get(hl["segment_id"])
            if not new_note_id or not new_seg_id:
                continue
            conn.execute(
                """INSERT INTO highlights
                     (note_id, segment_id, start_ms, end_ms, quote, kind, reason, importance, model, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    new_note_id,
                    new_seg_id,
                    hl["start_ms"],
                    hl["end_ms"],
                    hl["quote"],
                    hl.get("kind", "auto"),
                    hl.get("reason"),
                    hl.get("importance"),
                    hl.get("model"),
                    now,
                ),
            )

        for f in findings_in:
            new_note_id = note_id_map.get(f["note_id"])
            new_seg_id = segment_id_map.get(f["segment_id"])
            if not new_note_id or not new_seg_id:
                continue
            old_spk_id = f.get("speaker_id")
            new_spk_id = speaker_id_map.get(old_spk_id) if old_spk_id else None
            conn.execute(
                """INSERT INTO findings
                     (note_id, lens_id, lens_version, category, quote, segment_id,
                      start_ms, end_ms, speaker_id, confidence, rationale, model, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    new_note_id,
                    f["lens_id"],
                    f.get("lens_version", 1),
                    f["category"],
                    f["quote"],
                    new_seg_id,
                    f["start_ms"],
                    f["end_ms"],
                    new_spk_id,
                    f.get("confidence", 0.8),
                    f.get("rationale"),
                    f.get("model"),
                    now,
                ),
            )
            imported_findings += 1

    return {
        "imported_notes": imported_notes,
        "imported_segments": imported_segments,
        "imported_findings": imported_findings,
    }
