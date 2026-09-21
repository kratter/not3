"""Stage 2 — transcribe, via whisper.cpp.

We shell out to `whisper-cli` and parse its JSON rather than binding the
library. That is deliberate: it keeps the accelerated builds (CUDA on Windows,
Metal on Apple Silicon) as drop-in directories with no compiled Python
extension to match against the interpreter, which is the thing that makes
PyInstaller bundles break.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..config import AsrBackend, Settings

# whisper.cpp emits control tokens inline; they are not words.
_SPECIAL = re.compile(r"^\[_[A-Z]+_.*\]$")
_PROGRESS = re.compile(r"progress\s*=\s*(\d+)%")


class AsrError(RuntimeError):
    pass


@dataclass
class Word:
    text: str
    start_ms: int
    end_ms: int
    p: float


@dataclass
class Segment:
    idx: int
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None
    words: list[Word] = field(default_factory=list)

    def to_row(self) -> dict:
        return {
            "idx": self.idx,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "text": self.text,
            "confidence": self.confidence,
            "words_json": json.dumps(
                [{"t": w.text, "s": w.start_ms, "e": w.end_ms, "p": round(w.p, 4)}
                 for w in self.words],
                ensure_ascii=False,
            ) if self.words else None,
        }


@dataclass
class Transcript:
    segments: list[Segment]
    language: str | None
    backend: str
    model: str

    @property
    def text(self) -> str:
        return "\n".join(s.text for s in self.segments)


def _tokens_to_words(tokens: list[dict]) -> list[Word]:
    """Merge whisper tokens into words.

    whisper.cpp marks a word boundary with a leading space on the token, so a
    token that does not start with one is a continuation of the previous word.
    """
    words: list[Word] = []
    for tok in tokens:
        raw = tok.get("text", "")
        if not raw or _SPECIAL.match(raw.strip()):
            continue
        offsets = tok.get("offsets") or {}
        start = int(offsets.get("from", 0))
        end = int(offsets.get("to", start))
        p = float(tok.get("p", 0.0))

        if raw.startswith(" ") or not words:
            words.append(Word(text=raw.strip(), start_ms=start, end_ms=end, p=p))
        else:
            prev = words[-1]
            prev.text += raw
            prev.end_ms = max(prev.end_ms, end)
            prev.p = (prev.p + p) / 2
    return [w for w in words if w.text]


def parse_output(payload: dict) -> tuple[list[Segment], str | None]:
    language = (payload.get("result") or {}).get("language")
    segments: list[Segment] = []
    for idx, item in enumerate(payload.get("transcription") or []):
        text = (item.get("text") or "").strip()
        if not text:
            continue
        offsets = item.get("offsets") or {}
        words = _tokens_to_words(item.get("tokens") or [])
        confidence = sum(w.p for w in words) / len(words) if words else None
        segments.append(
            Segment(
                idx=len(segments),
                start_ms=int(offsets.get("from", 0)),
                end_ms=int(offsets.get("to", 0)),
                text=text,
                confidence=confidence,
                words=words,
            )
        )
    return segments, language


def build_command(
    backend: AsrBackend,
    audio: Path,
    out_prefix: Path,
    settings: Settings,
    *,
    use_vad: bool = True,
) -> list[str]:
    model = settings.asr_model_path()
    if not model.is_file():
        raise AsrError(
            f"ASR model not found: {model}\n"
            f"Download it into {settings.models_dir} "
            f"(e.g. ggml-large-v3-turbo.bin from huggingface.co/ggerganov/whisper.cpp)."
        )

    cmd = [
        str(backend.binary),
        "-m", str(model),
        "-f", str(audio),
        "-l", settings.language,
        "-ojf",                       # full JSON: segments plus per-token timings
        "-of", str(out_prefix),
        "-pp",                        # progress on stderr, for the UI
        "-np",                        # no banner
    ]
    if settings.asr_threads:
        cmd += ["-t", str(settings.asr_threads)]
    if not backend.accelerated:
        cmd += ["-ng"]

    vad_model = settings.vad_model_path()
    if use_vad and vad_model.is_file():
        cmd += ["--vad", "-vm", str(vad_model)]
    return cmd


def transcribe(
    audio: Path,
    settings: Settings,
    *,
    backend: AsrBackend | None = None,
    on_progress: Callable[[float, str], None] | None = None,
    check_cancelled: Callable[[], bool] | None = None,
    on_proc: Callable[[subprocess.Popen | None], None] | None = None,
) -> Transcript:
    """Run whisper.cpp over `audio`.

    Falls back down the backend ladder on failure: an accelerated build that
    crashes (missing driver, wrong CUDA arch, exhausted VRAM) must not cost the
    user their transcription when a CPU build is sitting right there.
    """
    from ..config import discover_asr_backends

    ladder = [backend] if backend else discover_asr_backends(settings.repo_root)
    if not ladder:
        raise AsrError(
            "No whisper.cpp build found under vendor/whisper. "
            "Run scripts/fetch_whisper.py."
        )

    last: Exception | None = None
    for candidate in ladder:
        if check_cancelled and check_cancelled():
            raise AsrError("Transcription cancelled by user")
        try:
            return _run(
                audio, settings, candidate, on_progress,
                check_cancelled=check_cancelled, on_proc=on_proc
            )
        except AsrError as exc:
            if "cancelled" in str(exc).lower():
                raise
            last = exc
            if on_progress:
                on_progress(0.0, f"{candidate.name} backend failed, trying next")
            continue
    raise AsrError(f"All ASR backends failed. Last error: {last}")


def _run(
    audio: Path,
    settings: Settings,
    backend: AsrBackend,
    on_progress: Callable[[float, str], None] | None,
    check_cancelled: Callable[[], bool] | None = None,
    on_proc: Callable[[subprocess.Popen | None], None] | None = None,
) -> Transcript:
    with tempfile.TemporaryDirectory(prefix="not3-asr-") as tmp:
        prefix = Path(tmp) / "out"
        cmd = build_command(backend, audio, prefix, settings)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if on_proc:
                on_proc(proc)
        except FileNotFoundError as exc:
            raise AsrError(f"whisper-cli not executable: {backend.binary}") from exc

        try:
            stderr_tail: list[str] = []
            assert proc.stderr is not None
            for line in proc.stderr:
                if check_cancelled and check_cancelled():
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    raise AsrError("Transcription cancelled by user")
                stderr_tail.append(line)
                del stderr_tail[:-40]
                if on_progress and (m := _PROGRESS.search(line)):
                    on_progress(int(m.group(1)) / 100.0, f"transcribing ({backend.name})")

            if proc.wait() != 0:
                if check_cancelled and check_cancelled():
                    raise AsrError("Transcription cancelled by user")
                raise AsrError(
                    f"whisper-cli ({backend.name}) exited {proc.returncode}:\n"
                    + "".join(stderr_tail[-12:]).strip()
                )
        finally:
            if on_proc:
                on_proc(None)

        result = prefix.with_suffix(".json")
        if not result.is_file():
            raise AsrError(f"whisper-cli ({backend.name}) produced no JSON output.")
        payload = json.loads(result.read_text(encoding="utf-8"))

    segments, language = parse_output(payload)
    if not segments:
        raise AsrError("Transcription produced no segments — is there speech in the file?")

    return Transcript(
        segments=segments,
        language=language,
        backend=backend.name,
        model=settings.asr_model,
    )
