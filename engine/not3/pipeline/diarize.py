"""Stage 2 — speaker diarization.

Separate who spoke when, attach speaker labels to transcript segments, and
populate the `speakers` table so downstream lenses and UI can attribute quotes.

Uses sherpa-onnx offline diarization by default: zero auth, local ONNX models,
runs on CPU or CUDA.
"""

from __future__ import annotations

import ctypes
import os
import pathlib
import sqlite3
import wave
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import db
from ..config import Settings

_DLL_INITIALIZED = False


def _ensure_onnxruntime_dll() -> None:
    """Pre-load modern onnxruntime.dll on Windows before importing sherpa-onnx.

    Windows prioritizes C:\\Windows\\System32\\onnxruntime.dll if present, which
    is often an obsolete build (e.g. ORT 1.17.1) that crashes with:
    'The requested API version [28] is not available'. Preloading from the
    installed onnxruntime package forces Windows to use the compatible runtime.
    """
    global _DLL_INITIALIZED
    if _DLL_INITIALIZED:
        return
    _DLL_INITIALIZED = True

    try:
        import onnxruntime  # noqa: F401
        ort_dir = pathlib.Path(onnxruntime.__file__).parent / "capi"
        ort_dll = ort_dir / "onnxruntime.dll"
        if ort_dll.is_file():
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(ort_dir))
            ctypes.CDLL(str(ort_dll))
    except Exception:
        pass


@dataclass(frozen=True)
class SpeakerTurn:
    start_ms: int
    end_ms: int
    speaker: str  # e.g. "SPEAKER_00"


class DiarizerBackend(ABC):
    """Abstract diarizer interface."""

    @abstractmethod
    def diarize(
        self,
        wav_path: Path,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> list[SpeakerTurn]:
        """Diarize a 16 kHz mono WAV file, returning non-overlapping speaker intervals."""
        ...


class SherpaDiarizer(DiarizerBackend):
    """Offline speaker diarization using sherpa-onnx."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        seg_path = settings.diarize_segmentation_path()
        emb_path = settings.diarize_embedding_path()

        if not seg_path.is_file():
            raise FileNotFoundError(
                f"Segmentation model missing at {seg_path}. "
                f"Run 'python scripts/fetch_diarize.py' to download it."
            )
        if not emb_path.is_file():
            raise FileNotFoundError(
                f"Embedding model missing at {emb_path}. "
                f"Run 'python scripts/fetch_diarize.py' to download it."
            )

        _ensure_onnxruntime_dll()
        import sherpa_onnx

        num_threads = settings.diarize_threads or max(2, min(8, (os.cpu_count() or 4) // 2))
        config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                    model=str(seg_path)
                ),
                num_threads=num_threads,
                provider="cpu",
            ),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=str(emb_path),
                num_threads=num_threads,
                provider="cpu",
            ),
            clustering=sherpa_onnx.FastClusteringConfig(
                num_clusters=-1,
                threshold=settings.diarize_threshold,
            ),
            min_duration_on=0.2,
            min_duration_off=0.3,
        )
        if not config.validate():
            raise RuntimeError("Invalid sherpa-onnx diarization configuration")

        self.diarizer = sherpa_onnx.OfflineSpeakerDiarization(config)

    def diarize(
        self,
        wav_path: Path,
        progress_cb: Callable[[float, str], None] | None = None,
        check_cancelled: Callable[[], bool] | None = None,
    ) -> list[SpeakerTurn]:
        import numpy as np

        if progress_cb:
            progress_cb(0.1, "reading audio for diarization...")

        with wave.open(str(wav_path), "rb") as wf:
            framerate = wf.getframerate()
            if framerate != 16000:
                raise ValueError(f"Expected 16 kHz audio, got {framerate} Hz")
            raw = wf.readframes(wf.getnframes())
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        if check_cancelled and check_cancelled():
            return []

        def _callback(processed_chunks: int, num_chunks: int) -> int:
            if check_cancelled and check_cancelled():
                return 1
            if progress_cb and num_chunks > 0:
                frac = min(1.0, processed_chunks / num_chunks)
                pct = int(frac * 100)
                progress_cb(max(0.1, frac), f"calculating speakers ({pct}%)")
            return 0

        result = self.diarizer.process(samples, callback=_callback)
        if check_cancelled and check_cancelled():
            return []
        raw_segments = result.sort_by_start_time()

        turns: list[SpeakerTurn] = []
        for seg in raw_segments:
            s_ms = int(round(seg.start * 1000))
            e_ms = int(round(seg.end * 1000))
            label = f"SPEAKER_{seg.speaker:02d}"
            turns.append(SpeakerTurn(start_ms=s_ms, end_ms=e_ms, speaker=label))

        return turns


def align_segments_to_speakers(
    segments: list[dict[str, Any]],
    turns: list[SpeakerTurn],
) -> dict[int, str]:
    """Map transcript segments to speaker labels by maximum temporal overlap.

    Returns mapping: {segment_id: speaker_label}.
    """
    if not segments or not turns:
        return {}

    mapping: dict[int, str] = {}

    for seg in segments:
        seg_id = seg["id"]
        s_start = seg["start_ms"]
        s_end = seg["end_ms"]
        seg_len = max(1, s_end - s_start)

        overlap_per_speaker: dict[str, int] = defaultdict(int)
        for turn in turns:
            if turn.end_ms <= s_start or turn.start_ms >= s_end:
                continue
            overlap = min(s_end, turn.end_ms) - max(s_start, turn.start_ms)
            if overlap > 0:
                overlap_per_speaker[turn.speaker] += overlap

        if overlap_per_speaker:
            # Pick speaker with the largest overlap
            best_speaker = max(overlap_per_speaker.items(), key=lambda x: x[1])[0]
            mapping[seg_id] = best_speaker
        else:
            # Fallback: assign to the closest turn if within 2000 ms
            closest_turn = min(
                turns,
                key=lambda t: min(abs(t.start_ms - s_end), abs(t.end_ms - s_start)),
            )
            dist = min(abs(closest_turn.start_ms - s_end), abs(closest_turn.end_ms - s_start))
            if dist <= 2000:
                mapping[seg_id] = closest_turn.speaker

    return mapping


def get_diarizer(settings: Settings) -> DiarizerBackend | None:
    """Factory for the configured diarizer backend."""
    if settings.diarizer == "off":
        return None
    if settings.diarizer == "sherpa":
        return SherpaDiarizer(settings)
    if settings.diarizer == "pyannote":
        # Reserved for future pyannote.audio backend
        raise NotImplementedError("pyannote backend requires pyannote.audio setup")
    raise ValueError(f"Unknown diarizer backend: {settings.diarizer}")


def diarize_note(
    conn: sqlite3.Connection,
    note_id: int,
    settings: Settings,
    progress_cb: Callable[[float, str], None] | None = None,
    diarizer: DiarizerBackend | None = None,
    check_cancelled: Callable[[], bool] | None = None,
) -> int:
    """Run speaker diarization on a note and map turns to transcript segments.

    Returns the number of speakers identified.
    """
    if settings.diarizer == "off":
        return 0

    note = conn.execute("SELECT media_path FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not note or not note["media_path"]:
        raise ValueError(f"Note {note_id} has no media to diarize")

    media_path = Path(note["media_path"])
    if not media_path.is_file():
        raise FileNotFoundError(f"Media file not found: {media_path}")

    if progress_cb:
        progress_cb(0.05, "loading diarizer models...")

    diarizer = diarizer or get_diarizer(settings)
    if not diarizer:
        return 0

    import inspect
    sig = inspect.signature(diarizer.diarize)
    if "check_cancelled" in sig.parameters:
        turns = diarizer.diarize(media_path, progress_cb=progress_cb, check_cancelled=check_cancelled)
    else:
        turns = diarizer.diarize(media_path, progress_cb=progress_cb)
    if not turns:
        if progress_cb:
            progress_cb(1.0, "no speech detected")
        return 0

    # Collect distinct speaker labels
    speakers = sorted({t.speaker for t in turns})

    with conn:
        # Register speakers
        for label in speakers:
            conn.execute(
                "INSERT OR IGNORE INTO speakers (note_id, label, display_name) VALUES (?, ?, NULL)",
                (note_id, label),
            )

        # Build speaker_label -> speaker_id map
        spk_rows = conn.execute(
            "SELECT id, label FROM speakers WHERE note_id = ?", (note_id,)
        ).fetchall()
        spk_map = {r["label"]: r["id"] for r in spk_rows}

        # Fetch all segments
        segments = [
            dict(r)
            for r in conn.execute(
                "SELECT id, start_ms, end_ms FROM segments WHERE note_id = ? ORDER BY idx",
                (note_id,),
            ).fetchall()
        ]

        alignment = align_segments_to_speakers(segments, turns)

        # Update segments with speaker_id
        for seg_id, spk_label in alignment.items():
            if sid := spk_map.get(spk_label):
                conn.execute(
                    "UPDATE segments SET speaker_id = ? WHERE id = ?",
                    (sid, seg_id),
                )

    if progress_cb:
        progress_cb(1.0, f"{len(speakers)} speakers identified")

    return len(speakers)
