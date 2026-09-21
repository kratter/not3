"""Runtime configuration and platform paths.

Every path and binary lookup goes through here. Nothing else in the engine is
allowed to know where things live, which is what keeps the Windows and Apple
Silicon builds from diverging.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "Not3"


def _data_dir() -> Path:
    override = os.environ.get("NOT3_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / APP_NAME.lower()


def _repo_root() -> Path:
    """Repo root in a dev checkout; the resource dir in a bundled app."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def host_arch() -> str:
    m = platform.machine().lower()
    if m in {"arm64", "aarch64"}:
        return "arm64"
    if m in {"amd64", "x86_64"}:
        return "x64"
    return m


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and host_arch() == "arm64"


@dataclass
class AsrBackend:
    """A concrete whisper.cpp build on disk."""

    name: str  # cuda | metal | cpu
    binary: Path

    @property
    def accelerated(self) -> bool:
        return self.name != "cpu"


def discover_asr_backends(root: Path | None = None) -> list[AsrBackend]:
    """Find installed whisper.cpp builds, best first.

    Ordering is the fallback ladder: an accelerated build is preferred, but a
    CPU build is always acceptable and always present. Apple Silicon reports
    `metal` because whisper.cpp uses Metal by default there — there is no
    separate binary, so the same CPU-named directory serves both and the label
    is decided by the platform rather than the path.
    """
    root = root or _repo_root()
    vendor_dirs = [root / "vendor" / "whisper"]
    if len(root.parents) >= 3:
        vendor_dirs.append(root.parents[2] / "vendor" / "whisper")
    vendor_dirs.extend([
        root.parent / "vendor" / "whisper",
        _data_dir() / "vendor" / "whisper",
    ])
    vendor = next((d for d in vendor_dirs if d.is_dir()), root / "vendor" / "whisper")
    exe = "whisper-cli.exe" if sys.platform == "win32" else "whisper-cli"
    arch = host_arch()

    candidates: list[tuple[str, Path]] = []
    if sys.platform == "win32":
        candidates = [("cuda", vendor / f"cuda-{arch}"), ("cpu", vendor / f"cpu-{arch}")]
    elif sys.platform == "darwin":
        label = "metal" if is_apple_silicon() else "cpu"
        candidates = [(label, vendor / f"macos-{arch}"), (label, vendor / "macos")]
    else:
        candidates = [("cuda", vendor / f"cuda-{arch}"), ("cpu", vendor / f"cpu-{arch}")]

    found: list[AsrBackend] = []
    seen: set[Path] = set()
    for name, directory in candidates:
        binary = directory / exe
        if binary.is_file() and binary not in seen:
            seen.add(binary)
            found.append(AsrBackend(name=name, binary=binary))

    # Last resort: whatever is on PATH.
    if not found:
        on_path = shutil.which("whisper-cli")
        if on_path:
            found.append(AsrBackend(name="cpu", binary=Path(on_path)))
    return found


@dataclass
class Settings:
    data_dir: Path = field(default_factory=_data_dir)
    repo_root: Path = field(default_factory=_repo_root)

    # ASR
    asr_model: str = "ggml-large-v3-turbo.bin"
    vad_model: str = "ggml-silero-v5.1.2.bin"
    asr_backend: str = "auto"  # auto | cuda | metal | cpu
    asr_threads: int = 0  # 0 = let whisper.cpp decide
    language: str = "auto"

    # Diarization
    diarizer: str = "sherpa"  # sherpa | pyannote | off
    diarize_segmentation_model: str = "sherpa-onnx-pyannote-segmentation-3-0.onnx"
    diarize_embedding_model: str = "wespeaker_en_voxceleb_CAM++_LM.onnx"
    diarize_threshold: float = 0.5
    diarize_threads: int = 2

    # LLM
    ollama_url: str = "http://127.0.0.1:11434"
    model_distill: str = "qwen3.5:9b"
    model_highlight: str = "qwen3.5:9b"
    model_lens: str = "qwen3.5:9b"
    model_embed: str = "embeddinggemma"
    llm_timeout_s: float = 600.0
    # Ollama defaults num_ctx to 4096 regardless of what the model supports,
    # which silently truncates answers to long prompts. The engine sizes the
    # window per request; this is the ceiling it may ask for. Raise it for a
    # model with a big context and VRAM to spare; lower it if the KV cache is
    # pushing the model out of VRAM.
    max_num_ctx: int = 32768

    # Chunking
    chunk_tokens: int = 2500
    chunk_overlap_tokens: int = 200

    # Anchoring
    quote_match_threshold: float = 90.0  # rapidfuzz partial ratio, 0-100

    export_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.export_dir is None:
            self.export_dir = self.data_dir / "export"

    # -- derived paths ----------------------------------------------------

    @property
    def db_path(self) -> Path:
        return self.data_dir / "not3.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def models_dir(self) -> Path:
        override = os.environ.get("NOT3_MODELS_DIR")
        if override:
            return Path(override).expanduser()
        candidates = [self.repo_root / "models"]
        if len(self.repo_root.parents) >= 3:
            candidates.append(self.repo_root.parents[2] / "models")
        candidates.append(self.data_dir / "models")
        for cand in candidates:
            if cand and cand.is_dir():
                return cand
        return self.data_dir / "models"

    @property
    def lenses_dir(self) -> Path:
        return Path(__file__).resolve().parent / "lenses"

    @property
    def user_lenses_dir(self) -> Path:
        """User-authored lenses. Shadow built-ins by reusing an id."""
        return self.data_dir / "lenses"

    @property
    def settings_path(self) -> Path:
        return self.data_dir / "settings.json"

    def llm_client(self):
        """The configured Ollama client. Built here so every call site gets
        the same context ceiling and timeout."""
        from .llm.ollama import Client
        return Client(self.ollama_url, self.llm_timeout_s, self.max_num_ctx)

    def asr_model_path(self) -> Path:
        return self.models_dir / self.asr_model

    def vad_model_path(self) -> Path:
        return self.models_dir / self.vad_model

    @property
    def diarize_models_dir(self) -> Path:
        return self.models_dir / "diarize"

    def diarize_segmentation_path(self) -> Path:
        return self.diarize_models_dir / self.diarize_segmentation_model

    def diarize_embedding_path(self) -> Path:
        return self.diarize_models_dir / self.diarize_embedding_model

    def ensure_dirs(self) -> None:
        for d in (
            self.data_dir,
            self.media_dir,
            self.models_dir,
            self.diarize_models_dir,
            self.user_lenses_dir,
            self.export_dir,
        ):
            Path(d).mkdir(parents=True, exist_ok=True)

    def pick_backend(self) -> AsrBackend | None:
        backends = discover_asr_backends(self.repo_root)
        if not backends:
            return None
        if self.asr_backend != "auto":
            for b in backends:
                if b.name == self.asr_backend:
                    return b
            # Asked for something absent: fall back rather than fail, but the
            # caller reports which backend actually ran.
        return backends[0]

    # -- persistence ------------------------------------------------------

    def save(self) -> None:
        self.ensure_dirs()
        data = {
            k: (str(v) if isinstance(v, Path) else v)
            for k, v in asdict(self).items()
            if k not in {"repo_root"}
        }
        self.settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        if s.settings_path.is_file():
            try:
                raw = json.loads(s.settings_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return s
            fields = {f for f in cls.__dataclass_fields__}
            for k, v in raw.items():
                if k in fields and k != "repo_root":
                    setattr(s, k, Path(v) if k in {"data_dir", "export_dir"} else v)
        return s


def ffmpeg_bin() -> str:
    return os.environ.get("NOT3_FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    return os.environ.get("NOT3_FFPROBE") or shutil.which("ffprobe") or "ffprobe"
