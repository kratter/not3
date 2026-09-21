"""HTTP API.

Bound to 127.0.0.1 and gated by a bearer token the shell passes in through the
environment. The UI is the only intended client, but "only reachable from
localhost" is not access control on a multi-user machine, so the token is not
optional in production.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from . import db
from .config import Settings, discover_asr_backends
from .setup import SetupManager
from .worker import ALL_STAGES, Worker

# WebView2 serves the app from http://tauri.localhost on Windows and
# tauri://localhost elsewhere, so every UI request is cross-origin and gets
# preflighted. Missing this is the classic Tauri v2 "works in the browser,
# fails in the app" bug.
ALLOWED_ORIGINS = [
    "http://tauri.localhost",
    "https://tauri.localhost",
    "tauri://localhost",
    "http://localhost:1420",  # vite dev server
    "http://127.0.0.1:1420",
]

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


class ImportRequest(BaseModel):
    path: str
    run: bool = True
    stages: list[str] | None = None
    lenses: list[str] | None = None
    style: str = "executive"


class TextNoteRequest(BaseModel):
    title: str | None = None
    text: str
    formalize: bool = True
    style: str = "formal"
    run: bool = True
    stages: list[str] | None = None
    lenses: list[str] | None = None


class RunRequest(BaseModel):
    stages: list[str] | None = None
    lenses: list[str] | None = None
    style: str = "executive"


class NotePatch(BaseModel):
    title: str | None = None


class LensPatch(BaseModel):
    enabled: bool


class SpeakerPatch(BaseModel):
    display_name: str


class SettingsPatch(BaseModel):
    asr_model: str | None = None
    asr_backend: str | None = None
    language: str | None = None
    diarizer: str | None = None
    ollama_url: str | None = None
    model_distill: str | None = None
    model_highlight: str | None = None
    model_lens: str | None = None
    chunk_tokens: int | None = Field(default=None, ge=500, le=32000)
    quote_match_threshold: float | None = Field(default=None, ge=50, le=100)
    export_dir: str | None = None


class SetupStartRequest(BaseModel):
    install_ollama: bool = True
    pull_llm: bool = True


class LensUploadRequest(BaseModel):
    yaml: str


class LibraryImportRequest(BaseModel):
    format: str
    version: int = 1
    notes: list[dict] = []
    speakers: list[dict] = []
    segments: list[dict] = []
    sections: list[dict] = []
    highlights: list[dict] = []
    findings: list[dict] = []


class AskRequest(BaseModel):
    query: str
    note_ids: list[int] | None = None


class VerifyPasswordRequest(BaseModel):
    password: str


class SetPasswordRequest(BaseModel):
    password: str
    current_password: str | None = None


class RemovePasswordRequest(BaseModel):
    current_password: str


class NoteChatRequest(BaseModel):
    prompt: str
    history: list[dict] = []
    model: str | None = None


class SectionUpdateRequest(BaseModel):
    content_md: str
    model: str | None = None


class PlusNotesRequest(BaseModel):
    content: str


class CreateCommentRequest(BaseModel):
    content: str
    author: str = "User"
    timestamp_ms: int | None = None



def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    settings.ensure_dirs()
    try:
        from .pipeline.diarize import _ensure_onnxruntime_dll
        _ensure_onnxruntime_dll()
    except Exception:
        pass
    token = os.environ.get("NOT3_TOKEN", "")

    worker_ref: dict[str, Worker] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        worker_ref["w"].start(asyncio.get_running_loop())
        from .pipeline.lens import sync_registry
        sync_registry(db.get(settings.db_path), settings)
        yield
        worker_ref["w"].stop()

    app = FastAPI(title="Not3 engine", version="0.1.0", docs_url=None,
                  redoc_url=None, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    worker = Worker(settings)
    worker_ref["w"] = worker
    setup_mgr = SetupManager(settings)
    app.state.settings = settings
    app.state.worker = worker
    app.state.setup_mgr = setup_mgr

    def require_token(request: Request) -> None:
        if not token:
            return  # dev mode: no shell, no token
        header = request.headers.get("authorization", "")
        supplied = header[7:] if header.lower().startswith("bearer ") else ""
        # compare_digest to keep the comparison time-independent
        import hmac
        if not hmac.compare_digest(supplied, token):
            raise HTTPException(status_code=401, detail="bad or missing token")

    guard = [Depends(require_token)]

    def conn() -> sqlite3.Connection:
        return db.get(settings.db_path)

    # -- health and status -------------------------------------------------

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "version": "0.1.0"}

    @app.get("/api/status", dependencies=guard)
    def status() -> dict:
        from .llm.ollama import Client
        s = Settings.load()
        client = Client(s.ollama_url, 5.0, s.max_num_ctx)
        ollama_up = client.available()
        return {
            "backends": [{"name": b.name, "path": str(b.binary)}
                         for b in discover_asr_backends(s.repo_root)],
            "asr_model": s.asr_model,
            "asr_model_present": s.asr_model_path().is_file(),
            "vad_model_present": s.vad_model_path().is_file(),
            "diarize_models_present": (
                s.diarize_segmentation_path().is_file() and s.diarize_embedding_path().is_file()
            ),
            "ollama": {"url": s.ollama_url, "available": ollama_up,
                       "models": client.models() if ollama_up else []},
            "worker": worker.status(),
            "data_dir": str(s.data_dir),
            "export_dir": str(s.export_dir),
        }

    @app.get("/api/system/metrics", dependencies=guard)
    def system_metrics() -> dict:
        from .system import get_system_metrics
        s = Settings.load()
        return get_system_metrics(s, worker.status())

    # -- app security & password ------------------------------------------

    @app.get("/api/auth/status")
    def auth_status() -> dict:
        s = Settings.load()
        return {"password_required": s.has_password()}

    @app.post("/api/auth/verify")
    def auth_verify(req: VerifyPasswordRequest) -> dict:
        s = Settings.load()
        return {"ok": s.verify_password(req.password)}

    @app.post("/api/auth/set_password", dependencies=guard)
    def auth_set_password(req: SetPasswordRequest) -> dict:
        s = Settings.load()
        if s.has_password() and not s.verify_password(req.current_password or ""):
            raise HTTPException(status_code=403, detail="Current password incorrect")
        if not req.password or len(req.password.strip()) == 0:
            raise HTTPException(status_code=400, detail="Password cannot be empty")
        s.set_password(req.password)
        app.state.settings = s
        worker.settings = s
        return {"ok": True}

    @app.post("/api/auth/remove_password", dependencies=guard)
    def auth_remove_password(req: RemovePasswordRequest) -> dict:
        s = Settings.load()
        if not s.verify_password(req.current_password or ""):
            raise HTTPException(status_code=403, detail="Current password incorrect")
        s.clear_password()
        app.state.settings = s
        worker.settings = s
        return {"ok": True}


    # -- setup and components ---------------------------------------------

    @app.get("/api/setup/status", dependencies=guard)
    def get_setup_status() -> dict:
        setup_mgr.settings = Settings.load()
        return setup_mgr.get_status()

    @app.post("/api/setup/start", dependencies=guard)
    async def start_setup(req: SetupStartRequest | None = None) -> dict:
        actual_req = req or SetupStartRequest()
        setup_mgr.settings = Settings.load()
        loop = asyncio.get_running_loop()
        loop.create_task(setup_mgr.start_setup(
            install_ollama=actual_req.install_ollama,
            pull_llm=actual_req.pull_llm,
        ))
        return {"started": True}

    @app.get("/api/setup/events", dependencies=guard)
    async def setup_events() -> StreamingResponse:
        async def event_generator():
            async for evt in setup_mgr.subscribe():
                yield f"data: {json.dumps(evt)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/settings", dependencies=guard)
    def get_settings() -> dict:
        s = Settings.load()
        return {
            "asr_model": s.asr_model, "asr_backend": s.asr_backend,
            "language": s.language, "diarizer": s.diarizer,
            "ollama_url": s.ollama_url, "model_distill": s.model_distill,
            "model_highlight": s.model_highlight, "model_lens": s.model_lens,
            "chunk_tokens": s.chunk_tokens,
            "quote_match_threshold": s.quote_match_threshold,
            "export_dir": str(s.export_dir),
        }

    @app.patch("/api/settings", dependencies=guard)
    def patch_settings(patch: SettingsPatch) -> dict:
        s = Settings.load()
        for key, value in patch.model_dump(exclude_none=True).items():
            setattr(s, key, Path(value) if key == "export_dir" else value)
        s.save()
        app.state.settings = s
        worker.settings = s
        return get_settings()

    # -- notes -------------------------------------------------------------

    @app.get("/api/notes", dependencies=guard)
    def list_notes() -> list[dict]:
        c = conn()
        out = []
        for row in db.list_notes(c):
            note = dict(row)
            note["segment_count"] = c.execute(
                "SELECT COUNT(*) FROM segments WHERE note_id = ?", (row["id"],)
            ).fetchone()[0]
            note["highlight_count"] = c.execute(
                "SELECT COUNT(*) FROM highlights WHERE note_id = ?", (row["id"],)
            ).fetchone()[0]
            note["finding_count"] = c.execute(
                "SELECT COUNT(*) FROM findings WHERE note_id = ?", (row["id"],)
            ).fetchone()[0]
            out.append(note)
        return out

    @app.post("/api/notes/import", dependencies=guard)
    def import_note(req: ImportRequest) -> dict:
        from .pipeline.ingest import IngestError, ingest

        s = Settings.load()
        try:
            ing = ingest(Path(req.path), s)
        except IngestError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        c = conn()
        existing = db.find_note_by_hash(c, ing.source_hash)
        if existing:
            return {"note_id": int(existing["id"]), "duplicate": True}

        note_id = db.create_note(
            c, source_path=str(ing.source_path), source_name=ing.source_name,
            source_hash=ing.source_hash, media_path=str(ing.media_path),
            duration_ms=ing.info.duration_ms, title=Path(ing.source_name).stem,
        )
        db.init_jobs(c, note_id)
        db.set_job(c, note_id, "ingest", state="done", progress=1.0)
        if req.run:
            worker.submit(note_id, req.stages or ALL_STAGES, lenses=req.lenses, style=req.style)
        return {"note_id": note_id, "duplicate": False}

    @app.post("/api/notes/text", dependencies=guard)
    def create_text_note(req: TextNoteRequest) -> dict:
        import hashlib
        from .llm.ollama import LlmError
        from .pipeline.formalize import formalize_notes, text_to_segments

        raw_text = req.text.strip()
        if not raw_text:
            raise HTTPException(status_code=400, detail="Note text cannot be empty.")

        s = Settings.load()
        final_text = raw_text
        if req.formalize:
            try:
                final_text = formalize_notes(raw_text, style=req.style, settings=s)
            except LlmError as exc:
                raise HTTPException(status_code=502, detail=f"Formalization error: {exc}") from exc

        rows, duration_ms = text_to_segments(final_text)
        if not rows:
            raise HTTPException(status_code=400, detail="No readable text found.")

        digest = hashlib.sha256(final_text.encode("utf-8")).hexdigest()
        c = conn()
        existing = db.find_note_by_hash(c, digest)
        if existing:
            return {"note_id": int(existing["id"]), "duplicate": True}

        title = req.title.strip() if req.title and req.title.strip() else ""
        if not title:
            first_line = rows[0]["text"]
            title = first_line[:60].strip()

        note_id = db.create_note(
            c,
            source_path="<manual>",
            source_name=f"{title}.txt" if title else "manual_note.txt",
            source_hash=digest,
            media_path="",
            duration_ms=duration_ms,
            title=title,
        )

        db.replace_segments(c, note_id, [
            {k: v for k, v in r.items() if not k.startswith("_")} for r in rows
        ])

        speakers = {r["_speaker"]: None for r in rows if r.get("_speaker")}
        if speakers:
            with db.tx(c):
                for label in speakers:
                    c.execute(
                        "INSERT OR IGNORE INTO speakers (note_id, label, display_name) "
                        "VALUES (?, ?, ?)", (note_id, label, label))
            mapping = {
                r["label"]: r["id"] for r in c.execute(
                    "SELECT id, label FROM speakers WHERE note_id = ?", (note_id,)).fetchall()
            }
            with db.tx(c):
                for r in rows:
                    if sid := mapping.get(r.get("_speaker")):
                        c.execute(
                            "UPDATE segments SET speaker_id = ? WHERE note_id = ? AND idx = ?",
                            (sid, note_id, r["idx"]))

        db.update_note(
            c,
            note_id,
            asr_backend="manual",
            asr_model="formalized" if req.formalize else "raw",
            language=s.language or "en",
        )

        db.init_jobs(c, note_id)
        db.set_job(c, note_id, "ingest", state="done", progress=1.0)
        db.set_job(c, note_id, "transcribe", state="skipped")
        db.set_job(c, note_id, "diarize", state="skipped")

        if req.run:
            stages = req.stages or ["distill", "highlight", "lens", "export"]
            worker.submit(note_id, stages, lenses=req.lenses, style=req.style)

        return {"note_id": note_id, "duplicate": False}

    @app.get("/api/notes/{note_id}", dependencies=guard)
    def get_note(note_id: int) -> dict:
        c = conn()
        note = db.get_note(c, note_id)
        if note is None:
            raise HTTPException(status_code=404, detail="no such note")
        return {
            "note": dict(note),
            "sections": db.get_sections(c, note_id),
            "jobs": rows_to_dicts(db.get_jobs(c, note_id)),
            "speakers": rows_to_dicts(c.execute(
                "SELECT * FROM speakers WHERE note_id = ? ORDER BY label",
                (note_id,)).fetchall()),
            "plus_notes": db.get_plus_notes(c, note_id),
            "comments": rows_to_dicts(db.get_comments(c, note_id)),
        }


    @app.patch("/api/notes/{note_id}", dependencies=guard)
    def patch_note(note_id: int, patch: NotePatch) -> dict:
        c = conn()
        if db.get_note(c, note_id) is None:
            raise HTTPException(status_code=404, detail="no such note")
        fields = patch.model_dump(exclude_none=True)
        if fields:
            db.update_note(c, note_id, **fields)
        return dict(db.get_note(c, note_id))

    @app.delete("/api/notes/{note_id}", dependencies=guard)
    def delete_note(note_id: int) -> dict:
        worker.cancel(note_id, update_db=False)
        c = conn()
        note = db.get_note(c, note_id)
        if note and note["media_path"]:
            try:
                p = Path(note["media_path"])
                if p.is_file():
                    p.unlink()
            except Exception:
                pass
        db.delete_note(c, note_id)
        return {"deleted": note_id}

    @app.get("/api/notes/{note_id}/segments", dependencies=guard)
    def get_segments(note_id: int) -> list[dict]:
        return rows_to_dicts(db.get_segments(conn(), note_id))

    @app.get("/api/notes/{note_id}/highlights", dependencies=guard)
    def get_highlights(note_id: int) -> list[dict]:
        return rows_to_dicts(db.get_highlights(conn(), note_id))

    @app.get("/api/notes/{note_id}/findings", dependencies=guard)
    def get_findings(note_id: int, lens_id: str | None = None) -> list[dict]:
        return rows_to_dicts(db.get_findings(conn(), note_id, lens_id))

    @app.get("/api/notes/{note_id}/jobs", dependencies=guard)
    def get_jobs(note_id: int) -> list[dict]:
        return rows_to_dicts(db.get_jobs(conn(), note_id))

    @app.post("/api/notes/{note_id}/run", dependencies=guard)
    def run_stages(note_id: int, req: RunRequest) -> dict:
        c = conn()
        note = db.get_note(c, note_id)
        if note is None:
            raise HTTPException(status_code=404, detail="no such note")
        if req.stages:
            stages = tuple(req.stages)
        elif not note["media_path"] or note["asr_backend"] == "manual":
            stages = ("distill", "highlight", "lens", "export")
        else:
            has_segments = c.execute(
                "SELECT 1 FROM segments WHERE note_id = ? LIMIT 1", (note_id,)
            ).fetchone() is not None
            if has_segments:
                stages = ("diarize", "distill", "highlight", "lens", "export")
            else:
                stages = ALL_STAGES
        unknown = set(stages) - set(ALL_STAGES)
        if unknown:
            raise HTTPException(status_code=400, detail=f"unknown stages: {sorted(unknown)}")
        worker.submit(note_id, stages, lenses=req.lenses, style=req.style)
        return {"queued": note_id, "stages": list(stages)}

    @app.get("/api/notes/{note_id}/export", dependencies=guard)
    def get_note_export(note_id: int) -> dict:
        from .pipeline import export as export_mod
        c = conn()
        note = db.get_note(c, note_id)
        if note is None:
            raise HTTPException(status_code=404, detail="no such note")
        lens_names = {
            r["id"]: r["name"] for r in c.execute("SELECT id, name FROM lenses").fetchall()
        }
        content = export_mod.render(
            note,
            db.get_segments(c, note_id),
            db.get_sections(c, note_id),
            db.get_highlights(c, note_id),
            db.get_findings(c, note_id),
            lens_names=lens_names,
            plus_notes=db.get_plus_notes(c, note_id),
            comments=db.get_comments(c, note_id),
        )
        name = export_mod.safe_filename(note["title"] or note["source_name"])
        export_path = settings.export_dir / f"{name}.md"
        return {
            "note_id": note_id,
            "title": note["title"] or note["source_name"],
            "filename": f"{name}.md",
            "path": str(export_path),
            "exists": export_path.is_file(),
            "content": content,
        }

    @app.post("/api/notes/{note_id}/export", dependencies=guard)
    def write_note_export(note_id: int) -> dict:
        from .pipeline import export as export_mod
        c = conn()
        note = db.get_note(c, note_id)
        if note is None:
            raise HTTPException(status_code=404, detail="no such note")
        path = export_mod.write(c, note_id, settings.export_dir)
        content = path.read_text(encoding="utf-8")
        return {
            "note_id": note_id,
            "path": str(path),
            "filename": path.name,
            "content": content,
        }

    # -- note AI chat & reformatting --------------------------------------

    @app.post("/api/notes/{note_id}/chat", dependencies=guard)
    def chat_note(note_id: int, req: NoteChatRequest) -> dict:
        c = conn()
        note = db.get_note(c, note_id)
        if note is None:
            raise HTTPException(status_code=404, detail="no such note")

        s = Settings.load()
        model = req.model or s.model_distill

        segments = db.get_segments(c, note_id)
        sections = db.get_sections(c, note_id)
        plus_notes = db.get_plus_notes(c, note_id)

        transcript_lines = []
        for seg in segments[:300]:
            spk = seg["speaker_name"] or seg["speaker_label"] or "Speaker"
            transcript_lines.append(f"{spk}: {seg['text']}")
        transcript_snippet = "\n".join(transcript_lines)

        sections_snippet = "\n\n".join(f"### {k.replace('_', ' ').title()}\n{v}" for k, v in sections.items())

        system_prompt = (
            "You are an expert AI editor, researcher, and clinical/executive intelligence assistant in Not3.\n"
            "You help the user review, query, polish, or reformat this audio note.\n"
            "Whenever asked to reformat, restructure, or rewrite the text (e.g. into an executive summary, bullet points, SOAP format, formal minutes, or polished prose):\n"
            "- Provide ready-to-use, clean Markdown with clear headings and formatting.\n"
            "- Do NOT include unnecessary conversational preamble; provide the formatted text directly so it can be pasted or applied to the note.\n\n"
            f"NOTE TITLE: {note['title'] or note['source_name']}\n"
            f"DURATION: {note['duration_ms'] // 1000}s\n\n"
            f"EXISTING SECTIONS:\n{sections_snippet or '(None yet)'}\n\n"
            f"PLUS NOTES (USER ADDENDUM):\n{plus_notes or '(None)'}\n\n"
            f"TRANSCRIPT EXCERPT:\n{transcript_snippet or '(No transcript available)'}"
        )

        messages = [{"role": "system", "content": system_prompt}]
        for m in req.history[-6:]:
            if m.get("role") in {"user", "assistant"} and m.get("content"):
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": req.prompt})

        client = s.llm_client()
        reply = ""
        if client.available():
            try:
                reply = client.chat(model=model, messages=messages)
            except Exception as e:
                reply = f"Error calling Ollama model '{model}': {e}"
        else:
            reply = (
                f"Ollama is currently unreachable at {s.ollama_url}. "
                f"Please ensure Ollama is running and model '{model}' is pulled to use AI Chat & Reformat."
            )

        return {"reply": reply, "model": model}

    # -- note sections update ---------------------------------------------

    @app.put("/api/notes/{note_id}/sections/{kind}", dependencies=guard)
    def update_note_section(note_id: int, kind: str, req: SectionUpdateRequest) -> dict:
        c = conn()
        if db.get_note(c, note_id) is None:
            raise HTTPException(status_code=404, detail="no such note")
        if kind not in {"summary", "key_points", "action_items", "topics"}:
            raise HTTPException(status_code=400, detail=f"invalid section kind: {kind}")
        db.upsert_section(c, note_id, kind, req.content_md, req.model or "ai-chat")
        return {"ok": True, "kind": kind, "content_md": req.content_md}

    # -- plus notes -------------------------------------------------------

    @app.get("/api/notes/{note_id}/plus_notes", dependencies=guard)
    def get_plus_notes(note_id: int) -> dict:
        c = conn()
        if db.get_note(c, note_id) is None:
            raise HTTPException(status_code=404, detail="no such note")
        return {"plus_notes": db.get_plus_notes(c, note_id)}

    @app.put("/api/notes/{note_id}/plus_notes", dependencies=guard)
    def update_plus_notes(note_id: int, req: PlusNotesRequest) -> dict:
        c = conn()
        if db.get_note(c, note_id) is None:
            raise HTTPException(status_code=404, detail="no such note")
        db.update_plus_notes(c, note_id, req.content)
        return {"ok": True, "plus_notes": req.content}

    # -- note comments ----------------------------------------------------

    @app.get("/api/notes/{note_id}/comments", dependencies=guard)
    def list_note_comments(note_id: int) -> list[dict]:
        c = conn()
        if db.get_note(c, note_id) is None:
            raise HTTPException(status_code=404, detail="no such note")
        return rows_to_dicts(db.get_comments(c, note_id))

    @app.post("/api/notes/{note_id}/comments", dependencies=guard)
    def add_note_comment(note_id: int, req: CreateCommentRequest) -> dict:
        c = conn()
        if db.get_note(c, note_id) is None:
            raise HTTPException(status_code=404, detail="no such note")
        cid = db.create_comment(
            c,
            note_id=note_id,
            content=req.content,
            author=req.author,
            timestamp_ms=req.timestamp_ms,
        )
        row = c.execute("SELECT * FROM note_comments WHERE id = ?", (cid,)).fetchone()
        return dict(row)

    @app.delete("/api/notes/{note_id}/comments/{comment_id}", dependencies=guard)
    def delete_note_comment(note_id: int, comment_id: int) -> dict:
        c = conn()
        db.delete_comment(c, comment_id)
        return {"ok": True, "deleted": comment_id}

    @app.post("/api/notes/{note_id}/cancel", dependencies=guard)
    def cancel(note_id: int) -> dict:
        c = conn()
        if db.get_note(c, note_id) is None:
            raise HTTPException(status_code=404, detail="no such note")
        worker.cancel(note_id)
        return {"cancelled": True, "note_id": note_id}

    @app.post("/api/notes/{note_id}/reset", dependencies=guard)
    def reset_note_endpoint(note_id: int) -> dict:
        c = conn()
        if db.get_note(c, note_id) is None:
            raise HTTPException(status_code=404, detail="no such note")
        worker.cancel(note_id, update_db=False)
        db.reset_note(c, note_id)
        worker.emit({"type": "stage", "note_id": note_id, "stage": "_", "state": "done"})
        return {"reset": True, "note_id": note_id}


    @app.patch("/api/speakers/{speaker_id}", dependencies=guard)
    def rename_speaker(speaker_id: int, patch: SpeakerPatch) -> dict:
        c = conn()
        with db.tx(c):
            c.execute("UPDATE speakers SET display_name = ? WHERE id = ?",
                      (patch.display_name, speaker_id))
        row = c.execute("SELECT * FROM speakers WHERE id = ?", (speaker_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="no such speaker")
        return dict(row)

    # -- audio -------------------------------------------------------------

    @app.get("/api/notes/{note_id}/audio")
    def audio(note_id: int, request: Request) -> Response:
        """Serve the normalized wav, with Range support.

        Deliberately unauthenticated: the token cannot be attached to an
        <audio src> and passing it in the query string would leak it into
        logs and history. The exposure is one local wav file the user already
        imported, reachable only from localhost.
        """
        note = db.get_note(conn(), note_id)
        if note is None or not note["media_path"]:
            raise HTTPException(status_code=404, detail="no audio for this note")
        path = Path(note["media_path"])
        if not path.is_file():
            raise HTTPException(status_code=404, detail="audio file is missing")

        size = path.stat().st_size
        start, end = 0, size - 1
        status = 200
        if match := _RANGE.match(request.headers.get("range", "")):
            first, last = match.group(1), match.group(2)
            if first:
                start = min(int(first), size - 1)
                end = min(int(last), size - 1) if last else size - 1
            elif last:  # suffix range: last N bytes
                start = max(0, size - int(last))
            status = 206

        length = max(0, end - start + 1)

        def stream() -> Iterator[bytes]:
            with path.open("rb") as fh:
                fh.seek(start)
                remaining = length
                while remaining > 0:
                    block = fh.read(min(1 << 18, remaining))
                    if not block:
                        break
                    remaining -= len(block)
                    yield block

        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Cache-Control": "no-cache",
        }
        if status == 206:
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return StreamingResponse(stream(), status_code=status,
                                 media_type="audio/wav", headers=headers)

    # -- lenses ------------------------------------------------------------

    @app.get("/api/lenses", dependencies=guard)
    def list_lenses() -> list[dict]:
        from .pipeline.lens import load_lenses, sync_registry

        s = Settings.load()
        c = conn()
        sync_registry(c, s)
        enabled = {r["id"]: bool(r["enabled"])
                   for r in c.execute("SELECT id, enabled FROM lenses").fetchall()}
        out = []
        for lens in load_lenses(s):
            out.append({
                "id": lens.id, "name": lens.name, "version": lens.version,
                "description": lens.description, "disclaimer": lens.disclaimer,
                "enabled": enabled.get(lens.id, True),
                "builtin": bool(lens.path and lens.path.parent == s.lenses_dir),
                "path": str(lens.path or ""),
                "categories": [
                    {"id": c_.id, "label": c_.label, "definition": c_.definition}
                    for c_ in lens.categories
                ],
            })
        return out

    @app.patch("/api/lenses/{lens_id}", dependencies=guard)
    def patch_lens(lens_id: str, patch: LensPatch) -> dict:
        c = conn()
        with db.tx(c):
            c.execute("UPDATE lenses SET enabled = ? WHERE id = ?",
                      (1 if patch.enabled else 0, lens_id))
        row = c.execute("SELECT * FROM lenses WHERE id = ?", (lens_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="no such lens")
        return dict(row)

    @app.get("/api/lens-runs", dependencies=guard)
    def lens_runs(limit: int = 100) -> list[dict]:
        """Anchoring telemetry: how often each lens proposes something that
        does not survive verification."""
        return rows_to_dicts(conn().execute(
            """SELECT lens_id, model,
                      COUNT(*) AS runs,
                      SUM(proposed) AS proposed,
                      SUM(kept) AS kept,
                      SUM(dropped_no_segment + dropped_no_quote + dropped_low_conf)
                        AS dropped,
                      AVG(duration_ms) AS avg_ms
                 FROM lens_runs
                GROUP BY lens_id, model
                ORDER BY lens_id
                LIMIT ?""", (limit,)).fetchall())

    @app.post("/api/lenses", dependencies=guard)
    def upload_lens(req: LensUploadRequest) -> dict:
        from .pipeline.lens import save_user_lens, sync_registry, LensError
        s = Settings.load()
        try:
            lens = save_user_lens(s, req.yaml)
        except LensError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        c = conn()
        sync_registry(c, s)
        return {
            "id": lens.id,
            "name": lens.name,
            "version": lens.version,
            "description": lens.description,
            "disclaimer": lens.disclaimer,
            "enabled": True,
            "builtin": False,
            "path": str(lens.path or ""),
            "categories": [
                {"id": c_.id, "label": c_.label, "definition": c_.definition}
                for c_ in lens.categories
            ],
        }

    @app.delete("/api/lenses/{lens_id}", dependencies=guard)
    def remove_lens(lens_id: str) -> dict:
        from .pipeline.lens import delete_user_lens, sync_registry, load_lenses
        s = Settings.load()
        deleted = delete_user_lens(s, lens_id)
        if not deleted:
            builtins = {l.id for l in load_lenses(s) if l.path and l.path.parent == s.lenses_dir}
            if lens_id in builtins:
                raise HTTPException(status_code=400, detail="Cannot delete shipped built-in lens.")
            raise HTTPException(status_code=404, detail="No such custom lens.")
        c = conn()
        sync_registry(c, s)
        return {"deleted": lens_id}

    @app.get("/api/lenses/{lens_id}/yaml", dependencies=guard)
    def get_lens_yaml(lens_id: str) -> dict:
        from .pipeline.lens import load_lenses
        s = Settings.load()
        lenses = {l.id: l for l in load_lenses(s)}
        lens = lenses.get(lens_id)
        if not lens or not lens.path or not lens.path.is_file():
            raise HTTPException(status_code=404, detail="Lens file not found.")
        return {
            "id": lens.id,
            "name": lens.name,
            "path": str(lens.path),
            "yaml": lens.path.read_text(encoding="utf-8"),
        }

    @app.get("/api/lenses/sample-template", dependencies=guard)
    def get_sample_lens_template() -> dict:
        s = Settings.load()
        sample_path = s.lenses_dir / "sample-custom-lens.yaml"
        if sample_path.is_file():
            text = sample_path.read_text(encoding="utf-8")
        else:
            text = "# Sample Lens Template\nid: sample_lens\nname: Sample Lens\nversion: 1\n..."
        return {"filename": "sample-custom-lens.yaml", "yaml": text}

    # -- library import/export & reference sample -------------------------

    @app.post("/api/library/sample", dependencies=guard)
    def seed_sample() -> dict:
        from .sample_data import seed_sample_library
        s = Settings.load()
        c = conn()
        notes = seed_sample_library(c, s)
        return {"seeded": True, "notes": notes}

    @app.get("/api/library/export", dependencies=guard)
    def export_library() -> dict:
        from .sample_data import export_library_json
        return export_library_json(conn())

    @app.post("/api/library/import", dependencies=guard)
    def import_library(req: LibraryImportRequest) -> dict:
        from .sample_data import import_library_json
        try:
            return import_library_json(conn(), req.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # -- insights & M7 ----------------------------------------------------

    @app.get("/api/insights/actions", dependencies=guard)
    def get_actions() -> list[dict]:
        return db.get_all_action_items(conn())

    @app.get("/api/insights/patterns", dependencies=guard)
    def get_patterns() -> dict:
        return db.get_pattern_matrix(conn())

    @app.get("/api/insights/search", dependencies=guard)
    def get_insights_search(
        q: str | None = None,
        lens_id: str | None = None,
        category: str | None = None,
        speaker_id: int | None = None,
        limit: int = 50,
    ) -> list[dict]:
        return db.search_insights(
            conn(), q=q, lens_id=lens_id, category=category, speaker_id=speaker_id, limit=limit
        )

    @app.post("/api/insights/ask", dependencies=guard)
    def ask_library(req: AskRequest) -> dict:
        from .insights import synthesize_library_query
        s = Settings.load()
        return synthesize_library_query(conn(), s, req.query, req.note_ids)

    # -- search ------------------------------------------------------------

    @app.get("/api/search", dependencies=guard)
    def search(q: str, limit: int = 50) -> list[dict]:
        if not q.strip():
            return []
        # Quote the term so FTS5 treats user input as a phrase rather than
        # syntax: an unescaped '"' or 'AND' would otherwise be an error.
        term = '"' + q.replace('"', '""') + '"'
        return rows_to_dicts(conn().execute(
            """SELECT s.id, s.note_id, s.start_ms, s.end_ms, s.text,
                      n.title, n.source_name,
                      -- Control characters as delimiters, not HTML tags: the
                      -- surrounding transcript text is not escaped by snippet(),
                      -- so returning markup would make the client either render
                      -- raw text as HTML or have to sanitise it.  and 
                      -- cannot occur in transcribed speech.
                      snippet(segments_fts, 0, char(2), char(3), '…', 12) AS snippet
                 FROM segments_fts
                 JOIN segments s ON s.id = segments_fts.rowid
                 JOIN notes n ON n.id = s.note_id
                WHERE segments_fts MATCH ?
                ORDER BY rank
                LIMIT ?""", (term, limit)).fetchall())

    # -- events ------------------------------------------------------------

    @app.get("/api/events")
    async def events(request: Request) -> StreamingResponse:
        """Server-sent progress.

        Consumed with fetch + ReadableStream rather than EventSource, because
        EventSource cannot set an Authorization header.
        """
        queue_ = worker.subscribe()

        async def generate() -> AsyncIterator[str]:
            yield "retry: 2000\n\n"
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue_.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"  # keep proxies and WebView2 happy
                        continue
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                worker.unsubscribe(queue_)

        return StreamingResponse(generate(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    return app
