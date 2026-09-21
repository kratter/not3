"""Stage 1 — ingest.

Take any file ffmpeg can open, hash it, normalize it to the 16 kHz mono PCM
whisper.cpp wants, and register a note. Video containers are fine: we only
ever keep the audio track.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings, ffmpeg_bin, ffprobe_bin

# Read in blocks rather than whole-file: these are recordings, not text files.
_HASH_BLOCK = 1024 * 1024


class IngestError(RuntimeError):
    pass


@dataclass
class MediaInfo:
    duration_ms: int
    sample_rate: int | None
    channels: int | None
    codec: str | None
    format_name: str | None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(_HASH_BLOCK):
            h.update(block)
    return h.hexdigest()


def probe(path: Path) -> MediaInfo:
    """ffprobe the source. Raises IngestError if there is no audio track."""
    cmd = [
        ffprobe_bin(), "-v", "error",
        "-show_entries", "format=duration,format_name",
        "-select_streams", "a:0",
        "-show_entries", "stream=sample_rate,channels,codec_name",
        "-of", "json", str(path),
    ]
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=120
        ).stdout
    except FileNotFoundError as exc:
        raise IngestError(
            "ffprobe not found. Install ffmpeg and put it on PATH, "
            "or set NOT3_FFPROBE."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise IngestError(f"ffprobe failed on {path.name}: {exc.stderr.strip()}") from exc

    data = json.loads(out or "{}")
    streams = data.get("streams") or []
    if not streams:
        raise IngestError(f"{path.name} has no audio track.")

    fmt = data.get("format") or {}
    stream = streams[0]
    try:
        duration_ms = int(float(fmt.get("duration") or 0) * 1000)
    except (TypeError, ValueError):
        duration_ms = 0

    return MediaInfo(
        duration_ms=duration_ms,
        sample_rate=int(stream["sample_rate"]) if stream.get("sample_rate") else None,
        channels=stream.get("channels"),
        codec=stream.get("codec_name"),
        format_name=fmt.get("format_name"),
    )


def to_wav16k(src: Path, dest: Path) -> Path:
    """Decode to 16 kHz mono signed-16 PCM — whisper.cpp's native input.

    Doing the resample here rather than letting whisper.cpp do it keeps the
    audio the UI plays byte-identical to the audio that produced the
    timestamps, so a highlight always lands on the words it was taken from.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin(), "-v", "error", "-y",
        "-i", str(src),
        "-vn",
        "-map", "0:a:0",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(dest),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=3600)
    except FileNotFoundError as exc:
        raise IngestError(
            "ffmpeg not found. Install ffmpeg and put it on PATH, or set NOT3_FFMPEG."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise IngestError(f"ffmpeg failed on {src.name}: {exc.stderr.strip()}") from exc
    if not dest.is_file() or dest.stat().st_size == 0:
        raise IngestError(f"ffmpeg produced no audio for {src.name}.")
    return dest


@dataclass
class Ingested:
    source_path: Path
    source_name: str
    source_hash: str
    media_path: Path
    info: MediaInfo


def ingest(src: Path, settings: Settings, *, keep_original: bool = False) -> Ingested:
    """Probe, hash and normalize. Pure filesystem work — no database."""
    src = Path(src).expanduser().resolve()
    if not src.is_file():
        raise IngestError(f"No such file: {src}")

    info = probe(src)
    digest = sha256_file(src)

    settings.ensure_dirs()
    media_path = settings.media_dir / f"{digest[:16]}.wav"
    if not media_path.is_file():
        to_wav16k(src, media_path)

    if keep_original:
        # Copy the source in so the note survives the original being moved or
        # deleted. Off by default: these files are large and usually already
        # somewhere the user manages.
        archived = settings.media_dir / f"{digest[:16]}{src.suffix}"
        if not archived.is_file():
            shutil.copy2(src, archived)
        src = archived

    return Ingested(
        source_path=src,
        source_name=src.name,
        source_hash=digest,
        media_path=media_path,
        info=info,
    )
