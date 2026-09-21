"""Command line entry point.

The whole pipeline is driven from here as well as from the API, so every stage
can be exercised and measured without the UI existing. That is what keeps the
expensive parts — ASR quality, prompt quality, anchoring drop rates — cheap to
iterate on.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import db
from .config import Settings, discover_asr_backends
from .pipeline import ingest as ingest_mod
from .pipeline.asr import AsrError, transcribe


def _fmt_ts(ms: int) -> str:
    s, ms = divmod(int(ms), 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _fmt_dur(ms: int) -> str:
    s = int(ms) // 1000
    return f"{s // 60}m{s % 60:02d}s"


def cmd_doctor(args: argparse.Namespace) -> int:
    """Report what the engine can actually do on this machine."""
    s = Settings.load()
    s.ensure_dirs()

    print(f"data dir     {s.data_dir}")
    print(f"models dir   {s.models_dir}")
    print(f"database     {s.db_path}  ({'exists' if s.db_path.is_file() else 'will be created'})")

    print("\nASR backends (best first):")
    backends = discover_asr_backends(s.repo_root)
    if not backends:
        print("  none found under vendor/whisper — run scripts/fetch_whisper.py")
    for b in backends:
        print(f"  {b.name:6} {b.binary}")

    print("\nmodels:")
    for label, path in (("asr", s.asr_model_path()), ("vad", s.vad_model_path())):
        mark = "ok     " if path.is_file() else "MISSING"
        size = f"{path.stat().st_size / 1e6:.0f} MB" if path.is_file() else ""
        print(f"  {label:4} {mark} {path.name} {size}")

    print("\ntools:")
    from .config import ffmpeg_bin, ffprobe_bin
    import shutil as _sh
    for label, binary in (("ffmpeg", ffmpeg_bin()), ("ffprobe", ffprobe_bin())):
        resolved = _sh.which(binary)
        print(f"  {label:8} {resolved or 'MISSING'}")

    ok = bool(backends) and s.asr_model_path().is_file()
    print("\n" + ("ready to transcribe." if ok else "not ready — see MISSING above."))
    return 0 if ok else 1


def cmd_transcribe(args: argparse.Namespace) -> int:
    s = Settings.load()
    if args.backend:
        s.asr_backend = args.backend
    if args.model:
        s.asr_model = args.model
    if args.language:
        s.language = args.language
    s.ensure_dirs()

    src = Path(args.file)
    conn = db.get(s.db_path)

    print(f"ingest     {src.name}")
    t0 = time.perf_counter()
    try:
        ing = ingest_mod.ingest(src, s)
    except ingest_mod.IngestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"           {_fmt_dur(ing.info.duration_ms)}  {ing.info.codec}  "
        f"{ing.info.sample_rate} Hz  {ing.info.channels}ch  "
        f"-> {ing.media_path.name}  ({time.perf_counter() - t0:.1f}s)"
    )

    existing = db.find_note_by_hash(conn, ing.source_hash)
    if existing and not args.force:
        print(f"           already imported as note {existing['id']} "
              f"(--force to re-transcribe)")
        note_id = int(existing["id"])
    elif existing:
        note_id = int(existing["id"])
    else:
        note_id = db.create_note(
            conn,
            source_path=str(ing.source_path),
            source_name=ing.source_name,
            source_hash=ing.source_hash,
            media_path=str(ing.media_path),
            duration_ms=ing.info.duration_ms,
            title=src.stem,
        )
    db.init_jobs(conn, note_id)

    if existing and not args.force:
        segs = db.get_segments(conn, note_id)
        if segs:
            print(f"           {len(segs)} segments already on disk; nothing to do")
            return 0

    backend = s.pick_backend()
    print(f"transcribe {s.asr_model} on {backend.name if backend else '?'}")
    db.update_note(conn, note_id, status="processing")
    db.set_job(conn, note_id, "transcribe", state="running")

    last = [-1.0]

    def progress(frac: float, message: str) -> None:
        if frac - last[0] >= 0.05 or frac >= 1.0:
            last[0] = frac
            db.set_job(conn, note_id, "transcribe", progress=frac, message=message)
            print(f"\r           {frac * 100:5.1f}%  {message}", end="", flush=True)

    t0 = time.perf_counter()
    try:
        tr = transcribe(ing.media_path, s, backend=backend, on_progress=progress)
    except AsrError as exc:
        print()
        db.set_job(conn, note_id, "transcribe", state="error", error=str(exc))
        db.update_note(conn, note_id, status="error", error=str(exc))
        print(f"error: {exc}", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - t0
    rtf = elapsed / (ing.info.duration_ms / 1000) if ing.info.duration_ms else 0
    print(f"\r           done in {elapsed:.1f}s  ({rtf:.3f}x realtime)          ")

    db.replace_segments(conn, note_id, [seg.to_row() for seg in tr.segments])
    db.update_note(
        conn, note_id,
        status="ready", language=tr.language,
        asr_backend=tr.backend, asr_model=tr.model,
    )
    db.set_job(conn, note_id, "transcribe", state="done", progress=1.0)

    words = sum(len(seg.words) for seg in tr.segments)
    print(f"           note {note_id}: {len(tr.segments)} segments, {words} words, "
          f"language={tr.language}")

    if args.print_transcript:
        print()
        for seg in tr.segments:
            conf = f"  ({seg.confidence:.2f})" if seg.confidence is not None else ""
            print(f"[{_fmt_ts(seg.start_ms)} -> {_fmt_ts(seg.end_ms)}]{conf}  {seg.text}")
    return 0


def cmd_import_transcript(args: argparse.Namespace) -> int:
    """Create a note from a plain-text transcript, no audio.

    Prompt and lens work needs a transcript, not a recording. Importing text
    directly makes that loop seconds long and deterministic, which is what
    lets a lens be tuned against the same material repeatedly.
    """
    import hashlib

    s = Settings.load()
    s.ensure_dirs()
    conn = db.get(s.db_path)

    path = Path(args.file)
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 1
    raw = path.read_text(encoding="utf-8")

    rows: list[dict] = []
    speakers: dict[str, None] = {}
    cursor_ms = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        speaker, _, text = line.partition(":")
        if not text.strip():
            speaker, text = "", line
        else:
            speakers[speaker.strip()] = None
        text = text.strip()
        # Roughly 150 spoken words a minute, so timings are plausible enough
        # for the UI and for chunk boundaries to behave realistically.
        duration = max(1200, int(len(text.split()) / 150 * 60_000))
        rows.append({
            "idx": len(rows), "start_ms": cursor_ms, "end_ms": cursor_ms + duration,
            "text": text, "confidence": 1.0, "words_json": None,
            "_speaker": speaker.strip(),
        })
        cursor_ms += duration + 200

    if not rows:
        print("no transcript lines found", file=sys.stderr)
        return 1

    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    existing = db.find_note_by_hash(conn, digest)
    if existing:
        db.delete_note(conn, int(existing["id"]))

    note_id = db.create_note(
        conn,
        source_path=str(path.resolve()), source_name=path.name, source_hash=digest,
        media_path="", duration_ms=cursor_ms, title=path.stem,
    )
    db.init_jobs(conn, note_id)
    db.replace_segments(conn, note_id, [
        {k: v for k, v in r.items() if not k.startswith("_")} for r in rows
    ])

    # Attach speakers so the diarization-dependent lenses have something real
    # to work with even when the source was text.
    if any(r["_speaker"] for r in rows):
        with db.tx(conn):
            for label in speakers:
                conn.execute(
                    "INSERT OR IGNORE INTO speakers (note_id, label, display_name) "
                    "VALUES (?, ?, ?)", (note_id, label, label))
        mapping = {
            r["label"]: r["id"] for r in conn.execute(
                "SELECT id, label FROM speakers WHERE note_id = ?", (note_id,)).fetchall()
        }
        with db.tx(conn):
            for r in rows:
                if sid := mapping.get(r["_speaker"]):
                    conn.execute(
                        "UPDATE segments SET speaker_id = ? WHERE note_id = ? AND idx = ?",
                        (sid, note_id, r["idx"]))

    db.update_note(conn, note_id, status="ready", language="en",
                   asr_backend="imported", asr_model="text")
    db.set_job(conn, note_id, "transcribe", state="skipped")
    print(f"note {note_id}: {len(rows)} segments, {len(speakers)} speakers, "
          f"{_fmt_dur(cursor_ms)} simulated")
    return 0


def cmd_process(args: argparse.Namespace) -> int:
    """Run the LLM stages over a note that has already been transcribed."""
    from .llm.chunker import to_chunk_segments
    from .llm.ollama import Client, LlmError
    from .pipeline import export as export_mod
    from .pipeline.distill import distill
    from .pipeline.highlight import find_highlights

    s = Settings.load()
    if args.model:
        s.model_distill = s.model_highlight = s.model_lens = args.model
    s.ensure_dirs()
    conn = db.get(s.db_path)

    note = db.get_note(conn, args.note_id)
    if note is None:
        print(f"no note {args.note_id}", file=sys.stderr)
        return 1
    rows = db.get_segments(conn, args.note_id)
    if not rows:
        print(f"note {args.note_id} has no transcript yet — run `not3 transcribe` first",
              file=sys.stderr)
        return 1

    client = s.llm_client()
    if not client.available():
        print(f"error: cannot reach Ollama at {s.ollama_url}", file=sys.stderr)
        return 1

    segments = to_chunk_segments(rows)
    print(f"note {args.note_id}: {len(rows)} segments, model {s.model_distill}")

    def progress(stage: str):
        def report(frac: float, message: str) -> None:
            db.set_job(conn, args.note_id, stage, progress=frac, message=message)
            print(f"\r  {stage:10} {frac * 100:5.1f}%  {message:<44}", end="", flush=True)
        return report

    # -- distill ----------------------------------------------------------
    db.set_job(conn, args.note_id, "distill", state="running")
    t0 = time.perf_counter()
    try:
        result = distill(segments, s, client, on_progress=progress("distill"))
    except LlmError as exc:
        print()
        db.set_job(conn, args.note_id, "distill", state="error", error=str(exc))
        print(f"error: {exc}", file=sys.stderr)
        return 1

    sections = {
        "summary": result.summary,
        "key_points": "\n".join(
            f"- {a.payload.get('text', a.quote)}  `[{_fmt_ts(a.start_ms)}]`"
            for a in result.key_points
        ),
        "action_items": "\n".join(
            f"- {a.payload.get('text', a.quote)}"
            + (f" — *{a.payload['owner']}*" if a.payload.get("owner") else "")
            + f"  `[{_fmt_ts(a.start_ms)}]`"
            for a in result.action_items
        ),
        "topics": ", ".join(result.topics),
    }
    db.replace_sections(conn, args.note_id, sections, result.model)
    if result.title and not args.keep_title:
        db.update_note(conn, args.note_id, title=result.title)
    db.set_job(conn, args.note_id, "distill", state="done", progress=1.0)
    print(f"\r  distill    {time.perf_counter() - t0:5.1f}s  "
          f"{len(result.key_points)} key points, {len(result.action_items)} actions, "
          f"anchoring: {result.stats.summary():<30}")

    # -- highlight --------------------------------------------------------
    db.set_job(conn, args.note_id, "highlight", state="running")
    t0 = time.perf_counter()
    try:
        hl = find_highlights(segments, s, client, on_progress=progress("highlight"))
    except LlmError as exc:
        print()
        db.set_job(conn, args.note_id, "highlight", state="error", error=str(exc))
        print(f"error: {exc}", file=sys.stderr)
        return 1

    db.replace_highlights(
        conn, args.note_id,
        [{"segment_id": a.segment_id, "start_ms": a.start_ms, "end_ms": a.end_ms,
          "quote": a.quote, "reason": a.payload.get("reason"),
          "importance": a.confidence} for a in hl.highlights],
        hl.model,
    )
    db.set_job(conn, args.note_id, "highlight", state="done", progress=1.0)
    print(f"\r  highlight  {time.perf_counter() - t0:5.1f}s  "
          f"{len(hl.highlights)} highlights, anchoring: {hl.stats.summary():<30}")

    # -- export -----------------------------------------------------------
    db.set_job(conn, args.note_id, "export", state="running")
    path = export_mod.write(conn, args.note_id, s.export_dir)
    db.set_job(conn, args.note_id, "export", state="done", progress=1.0)
    db.update_note(conn, args.note_id, status="ready")
    print(f"  export     {path}")

    if args.print_note:
        print()
        print(path.read_text(encoding="utf-8"))
    return 0


def cmd_lenses(args: argparse.Namespace) -> int:
    from .pipeline.lens import load_lenses, sync_registry

    s = Settings.load()
    s.ensure_dirs()
    conn = db.get(s.db_path)
    sync_registry(conn, s)

    lenses = load_lenses(s)
    if not lenses:
        print("no lenses found")
        return 0
    enabled = {r["id"]: r["enabled"] for r in
               conn.execute("SELECT id, enabled FROM lenses").fetchall()}
    for lens in lenses:
        mark = "on " if enabled.get(lens.id, 1) else "off"
        builtin = "built-in" if lens.path and lens.path.parent == s.lenses_dir else "user"
        print(f"  [{mark}] {lens.id:24} v{lens.version}  "
              f"{len(lens.categories):>2} categories  {builtin:8} {lens.name}")
    print(f"\ndrop your own into {s.user_lenses_dir}")
    print("a user lens reusing a built-in id replaces it")
    return 0


def cmd_lens(args: argparse.Namespace) -> int:
    """Run the enabled lenses over a note."""
    from .llm.chunker import to_chunk_segments
    from .llm.ollama import Client, LlmError
    from .pipeline import export as export_mod
    from .pipeline.lens import load_lenses, run_lens, sync_registry

    s = Settings.load()
    if args.model:
        s.model_lens = args.model
    s.ensure_dirs()
    conn = db.get(s.db_path)

    if db.get_note(conn, args.note_id) is None:
        print(f"no note {args.note_id}", file=sys.stderr)
        return 1
    rows = db.get_segments(conn, args.note_id)
    if not rows:
        print(f"note {args.note_id} has no transcript yet", file=sys.stderr)
        return 1

    sync_registry(conn, s)
    lenses = load_lenses(s)
    if args.lens:
        lenses = [l for l in lenses if l.id in set(args.lens)]
        if not lenses:
            print(f"no lens matching {args.lens}", file=sys.stderr)
            return 1
    else:
        disabled = {r["id"] for r in conn.execute(
            "SELECT id FROM lenses WHERE enabled = 0").fetchall()}
        lenses = [l for l in lenses if l.id not in disabled]

    client = s.llm_client()
    if not client.available():
        print(f"error: cannot reach Ollama at {s.ollama_url}", file=sys.stderr)
        return 1

    segments = to_chunk_segments(rows)
    has_speakers = any(r["speaker_label"] for r in rows)
    print(f"note {args.note_id}: {len(rows)} segments, "
          f"{'speakers present' if has_speakers else 'no speakers'}, model {s.model_lens}")

    db.set_job(conn, args.note_id, "lens", state="running")
    total_kept = 0
    for lens in lenses:
        if lens.requires_speakers and not has_speakers:
            print(f"  {lens.id:24} skipped — needs speaker separation")
            continue

        def report(frac: float, message: str) -> None:
            print(f"\r  {lens.id:24} {frac * 100:5.1f}%  {message:<36}", end="", flush=True)

        try:
            result = run_lens(lens, segments, s, client, on_progress=report)
        except LlmError as exc:
            print()
            db.set_job(conn, args.note_id, "lens", state="error", error=str(exc))
            print(f"error: {exc}", file=sys.stderr)
            return 1

        db.replace_findings(
            conn, args.note_id, lens.id,
            [{"lens_version": lens.version, "category": a.payload.get("category", ""),
              "quote": a.quote, "segment_id": a.segment_id, "start_ms": a.start_ms,
              "end_ms": a.end_ms, "confidence": a.confidence,
              "rationale": a.payload.get("rationale")} for a in result.findings],
            result.model,
        )
        db.record_lens_run(conn, args.note_id, lens.id, lens.version,
                           result.model, result.stats, result.duration_ms)
        total_kept += len(result.findings)
        print(f"\r  {lens.id:24} {result.duration_ms / 1000:5.1f}s  "
              f"{len(result.findings):>2} findings   {result.stats.summary():<40}")

        if args.verbose:
            for a in result.findings:
                label = str(a.payload.get("category", "")).replace("_", " ")
                who = f"{a.speaker}: " if a.speaker else ""
                print(f"       [{_fmt_ts(a.start_ms)}] {label:24} {a.confidence:.0%}  "
                      f"{who}“{a.quote}”")
                if rationale := a.payload.get("rationale"):
                    print(f"       {'':>36} {rationale}")

    db.set_job(conn, args.note_id, "lens", state="done", progress=1.0)
    path = export_mod.write(conn, args.note_id, s.export_dir)
    print(f"  {'export':24} {path}")
    print(f"\n{total_kept} findings across {len(lenses)} lenses")
    return 0


def cmd_notes(args: argparse.Namespace) -> int:
    s = Settings.load()
    conn = db.get(s.db_path)
    rows = db.list_notes(conn)
    if not rows:
        print("no notes yet")
        return 0
    print(f"{'id':>4}  {'status':9} {'dur':>7}  {'segs':>5}  {'lang':4} {'backend':7} title")
    for r in rows:
        n = conn.execute(
            "SELECT COUNT(*) FROM segments WHERE note_id = ?", (r["id"],)
        ).fetchone()[0]
        print(f"{r['id']:>4}  {r['status']:9} {_fmt_dur(r['duration_ms']):>7}  "
              f"{n:>5}  {(r['language'] or '-'):4} {(r['asr_backend'] or '-'):7} "
              f"{r['title'] or r['source_name']}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    s = Settings.load()
    conn = db.get(s.db_path)
    note = db.get_note(conn, args.note_id)
    if not note:
        print(f"no note {args.note_id}", file=sys.stderr)
        return 1
    print(f"# {note['title'] or note['source_name']}")
    print(f"  {_fmt_dur(note['duration_ms'])}  {note['language']}  "
          f"{note['asr_model']} on {note['asr_backend']}\n")
    for seg in db.get_segments(conn, args.note_id):
        who = seg["speaker_name"] or seg["speaker_label"] or ""
        who = f"{who}: " if who else ""
        print(f"[{_fmt_ts(seg['start_ms'])}]  {who}{seg['text']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="not3", description="Not3 engine")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="report what this machine can do").set_defaults(
        func=cmd_doctor
    )

    t = sub.add_parser("transcribe", help="ingest and transcribe an audio/video file")
    t.add_argument("file")
    t.add_argument("--backend", choices=["auto", "cuda", "metal", "cpu"])
    t.add_argument("--model", help="ggml model filename inside the models dir")
    t.add_argument("--language", help="'auto' or an ISO code")
    t.add_argument("--force", action="store_true", help="re-transcribe if already imported")
    t.add_argument("--print", dest="print_transcript", action="store_true")
    t.set_defaults(func=cmd_transcribe)

    it = sub.add_parser("import-transcript",
                        help="create a note from a plain-text transcript (no audio)")
    it.add_argument("file")
    it.set_defaults(func=cmd_import_transcript)

    pr = sub.add_parser("process", help="distill, highlight and export a transcribed note")
    pr.add_argument("note_id", type=int)
    pr.add_argument("--model", help="override the Ollama model for all LLM stages")
    pr.add_argument("--keep-title", action="store_true",
                    help="do not replace the title with the generated one")
    pr.add_argument("--print", dest="print_note", action="store_true")
    pr.set_defaults(func=cmd_process)

    sub.add_parser("lenses", help="list available lenses").set_defaults(func=cmd_lenses)

    ln = sub.add_parser("lens", help="run pattern lenses over a note")
    ln.add_argument("note_id", type=int)
    ln.add_argument("--lens", action="append", help="run only this lens id (repeatable)")
    ln.add_argument("--model", help="override the Ollama model")
    ln.add_argument("-v", "--verbose", action="store_true", help="print each finding")
    ln.set_defaults(func=cmd_lens)

    sub.add_parser("notes", help="list notes").set_defaults(func=cmd_notes)

    sh = sub.add_parser("show", help="print a note's transcript")
    sh.add_argument("note_id", type=int)
    sh.set_defaults(func=cmd_show)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
