"""Background pipeline execution.

One worker thread, one queue. Transcription saturates the GPU and the LLM
stages saturate it again, so running jobs concurrently would make every job
slower and none of them finish sooner. Serializing is the honest design.

Progress is written to the `jobs` table (so it survives a restart and the UI
can recover state on reconnect) *and* pushed to subscribers for SSE, because
polling a database for a progress bar is a waste of both.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
import traceback
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import db
from .config import Settings

ALL_STAGES = ("transcribe", "diarize", "distill", "highlight", "lens", "export")


@dataclass
class Job:
    note_id: int
    stages: tuple[str, ...]
    source: Path | None = None  # set when the note still has to be ingested
    cancelled: bool = False
    submitted_at: float = field(default_factory=time.time)
    lenses: tuple[str, ...] | None = None
    style: str = "executive"


class Worker:
    """Runs pipeline stages off the request thread."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._queue: queue.Queue[Job | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self._current: Job | None = None
        self._current_proc: subprocess.Popen | None = None
        self._stop = threading.Event()

    def _set_current_proc(self, proc: subprocess.Popen | None) -> None:
        with self._lock:
            self._current_proc = proc

    # -- lifecycle ---------------------------------------------------------

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._recover_orphans()
        self._thread = threading.Thread(target=self._run, name="not3-worker", daemon=True)
        self._thread.start()

    def _recover_orphans(self) -> None:
        """Clear any jobs left in 'running' or 'pending' state from an interrupted session."""
        conn = db.get(self.settings.db_path)
        db.reset_stale_jobs(conn)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=timeout)

    # -- submission --------------------------------------------------------

    def submit(
        self,
        note_id: int,
        stages: Iterable[str] | None = None,
        source: Path | None = None,
        lenses: Iterable[str] | None = None,
        style: str = "executive",
    ) -> Job:
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="not3-worker", daemon=True)
            self._thread.start()

        # If there's an existing job running or queued for this note, cancel it cleanly first
        self.cancel(note_id, update_db=False)

        job = Job(
            note_id=note_id,
            stages=tuple(stages or ALL_STAGES),
            source=source,
            lenses=tuple(lenses) if lenses is not None else None,
            style=style,
        )
        conn = db.get(self.settings.db_path)
        with db.tx(conn):
            conn.execute("DELETE FROM jobs WHERE note_id = ? AND stage = 'embed'", (note_id,))
            conn.execute("UPDATE jobs SET error = NULL WHERE note_id = ?", (note_id,))
        db.init_jobs(conn, note_id)
        for stage in job.stages:
            db.set_job(conn, note_id, stage, state="pending", progress=0.0, message="queued", error=None)
        db.update_note(conn, note_id, status="processing", error=None)
        self._queue.put(job)
        self.emit({"type": "queued", "note_id": note_id, "stages": list(job.stages)})
        return job

    def cancel(self, note_id: int, update_db: bool = True) -> bool:
        """Cancel a queued job, or interrupt a running one and update SQLite state."""
        with self._lock:
            if self._current and self._current.note_id == note_id:
                self._current.cancelled = True
                if self._current_proc:
                    try:
                        self._current_proc.terminate()
                        self._current_proc.kill()
                    except Exception:
                        pass
        pending: list[Job] = []
        try:
            while True:
                job = self._queue.get_nowait()
                if job is None:
                    continue
                if job.note_id != note_id:
                    pending.append(job)
        except queue.Empty:
            pass
        for job in pending:
            self._queue.put(job)

        if update_db:
            conn = db.get(self.settings.db_path)
            db.cancel_note_jobs(conn, note_id)
            self.emit({"type": "cancelled", "note_id": note_id})

        return True

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._current is not None

    def status(self) -> dict[str, Any]:
        with self._lock:
            current = self._current
        return {
            "busy": current is not None,
            "note_id": current.note_id if current else None,
            "stage": None,
            "queued": self._queue.qsize(),
        }

    # -- events ------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def emit(self, event: dict[str, Any]) -> None:
        """Push an event to SSE subscribers. Safe to call from any thread."""
        loop = self._loop
        if loop is None or not self._subscribers:
            return

        def deliver() -> None:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    # A subscriber that cannot keep up gets dropped events
                    # rather than blocking the pipeline. The UI reconciles
                    # from the jobs table on reconnect.
                    pass

        try:
            loop.call_soon_threadsafe(deliver)
        except RuntimeError:
            pass  # loop closed during shutdown

    # -- execution ---------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            job = self._queue.get()
            if job is None:
                break
            with self._lock:
                self._current = job
            try:
                self._execute(job)
            except Exception:  # noqa: BLE001 - a worker thread must not die
                traceback.print_exc()
            finally:
                with self._lock:
                    self._current = None

    def _execute(self, job: Job) -> None:
        conn = db.get(self.settings.db_path)
        settings = Settings.load()

        def progress(stage: str):
            def report(frac: float, message: str) -> None:
                db.set_job(conn, job.note_id, stage, progress=frac, message=message)
                self.emit({"type": "progress", "note_id": job.note_id, "stage": stage,
                           "progress": frac, "message": message})
            return report

        def begin(stage: str) -> None:
            db.set_job(conn, job.note_id, stage, state="running", progress=0.0)
            self.emit({"type": "stage", "note_id": job.note_id,
                       "stage": stage, "state": "running"})

        def finish(stage: str, state: str = "done", error: str | None = None) -> None:
            db.set_job(conn, job.note_id, stage, state=state,
                       progress=1.0 if state == "done" else None, error=error)
            self.emit({"type": "stage", "note_id": job.note_id, "stage": stage,
                       "state": state, "error": error})

        for stage in job.stages:
            if job.cancelled:
                db.set_job(conn, job.note_id, stage, state="error", message="cancelled", error="Cancelled by user")
                self.emit({"type": "cancelled", "note_id": job.note_id, "stage": stage})
                continue
            begin(stage)
            try:
                self._stage(stage, job, settings, conn, progress(stage))
            except Exception as exc:  # noqa: BLE001
                err_msg = "Cancelled by user" if job.cancelled else str(exc)
                finish(stage, "error", err_msg)
                db.update_note(conn, job.note_id, status="error", error=err_msg)
                self.emit({"type": "cancelled" if job.cancelled else "error",
                           "note_id": job.note_id, "stage": stage, "error": err_msg})
                return
            if job.cancelled:
                finish(stage, "error", "Cancelled by user")
                db.update_note(conn, job.note_id, status="error", error="Cancelled by user")
                self.emit({"type": "cancelled", "note_id": job.note_id, "stage": stage})
                return
            finish(stage)

        if job.cancelled:
            db.update_note(conn, job.note_id, status="error", error="Cancelled by user")
            self.emit({"type": "cancelled", "note_id": job.note_id})
        else:
            db.update_note(conn, job.note_id, status="ready", error=None)
            self.emit({"type": "done", "note_id": job.note_id})

    def _stage(self, stage: str, job: Job, settings: Settings, conn, report) -> None:
        from .llm.chunker import to_chunk_segments
        from .pipeline import export as export_mod
        from .pipeline.asr import transcribe
        from .pipeline.distill import distill
        from .pipeline.highlight import find_highlights
        from .pipeline.lens import load_lenses, run_lens, sync_registry

        note = db.get_note(conn, job.note_id)
        if note is None:
            raise ValueError(f"note {job.note_id} no longer exists")

        if stage == "transcribe":
            media = Path(note["media_path"])
            if not media.is_file():
                raise FileNotFoundError(f"audio missing: {media}")
            backend = settings.pick_backend()
            tr = transcribe(
                media, settings, backend=backend, on_progress=report,
                check_cancelled=lambda: job.cancelled,
                on_proc=self._set_current_proc,
            )
            db.replace_segments(conn, job.note_id, [s.to_row() for s in tr.segments])
            db.update_note(conn, job.note_id, language=tr.language,
                           asr_backend=tr.backend, asr_model=tr.model)
            return

        if stage == "diarize":
            if settings.diarizer == "off":
                report(1.0, "diarization disabled")
                return
            from .pipeline.diarize import diarize_note
            try:
                num_spk = diarize_note(
                    conn, job.note_id, settings, progress_cb=report,
                    check_cancelled=lambda: job.cancelled,
                )
                report(1.0, f"{num_spk} speaker{'s' if num_spk != 1 else ''} found")
            except (FileNotFoundError, RuntimeError) as exc:
                # If models haven't been downloaded yet, warn and continue pipeline
                report(1.0, f"diarization skipped: {exc}")
            return

        rows = db.get_segments(conn, job.note_id)
        if not rows:
            raise ValueError("no transcript — run transcribe first")
        segments = to_chunk_segments(rows)
        client = settings.llm_client()

        if stage == "distill":
            result = distill(segments, settings, client, style=job.style, on_progress=report)
            db.replace_sections(conn, job.note_id, {
                "summary": result.summary,
                "key_points": "\n".join(
                    f"- {a.payload.get('text', a.quote)}" for a in result.key_points),
                "action_items": "\n".join(
                    f"- {a.payload.get('text', a.quote)}" for a in result.action_items),
                "topics": ", ".join(result.topics),
            }, result.model)
            if result.title:
                db.update_note(conn, job.note_id, title=result.title)

        elif stage == "highlight":
            result = find_highlights(segments, settings, client, on_progress=report)
            db.replace_highlights(conn, job.note_id, [
                {"segment_id": a.segment_id, "start_ms": a.start_ms, "end_ms": a.end_ms,
                 "quote": a.quote, "reason": a.payload.get("reason"),
                 "importance": a.confidence} for a in result.highlights
            ], result.model)

        elif stage == "lens":
            sync_registry(conn, settings)
            disabled = {r["id"] for r in
                        conn.execute("SELECT id FROM lenses WHERE enabled = 0").fetchall()}
            lenses = [l for l in load_lenses(settings) if l.id not in disabled]
            if job.lenses is not None:
                wanted = set(job.lenses)
                lenses = [l for l in lenses if l.id in wanted]
            has_speakers = any(r["speaker_label"] for r in rows)
            failures: list[str] = []
            for i, lens in enumerate(lenses):
                if job.cancelled:
                    break
                if lens.requires_speakers and not has_speakers:
                    continue

                def lens_report(frac: float, message: str, i=i) -> None:
                    report((i + frac) / max(1, len(lenses)), message)

                try:
                    result = run_lens(lens, segments, settings, client,
                                      on_progress=lens_report)
                except Exception as exc:  # noqa: BLE001
                    # A lens that fails — a prompt too large for the model, a
                    # malformed edit to its YAML — costs its own findings and
                    # nothing else. Reporting it and moving on beats losing
                    # the other lenses and the rest of the pipeline.
                    failures.append(f"{lens.name}: {exc}")
                    self.emit({"type": "lens-error", "note_id": job.note_id,
                               "lens_id": lens.id, "error": str(exc)})
                    continue
                db.replace_findings(conn, job.note_id, lens.id, [
                    {"lens_version": lens.version,
                     "category": a.payload.get("category", ""), "quote": a.quote,
                     "segment_id": a.segment_id, "start_ms": a.start_ms,
                     "end_ms": a.end_ms, "confidence": a.confidence,
                     "rationale": a.payload.get("rationale")} for a in result.findings
                ], result.model)
                db.record_lens_run(conn, job.note_id, lens.id, lens.version,
                                   result.model, result.stats, result.duration_ms)

            if failures and len(failures) == len(lenses):
                raise RuntimeError("; ".join(failures))
            if failures:
                report(1.0, f"{len(failures)} of {len(lenses)} lenses failed")

        elif stage == "export":
            export_mod.write(conn, job.note_id, settings.export_dir)

        else:
            raise ValueError(f"unknown stage: {stage}")
