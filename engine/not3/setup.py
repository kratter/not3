"""Modular setup manager for Not3.

Handles detection, downloading, and installation of:
- Whisper.cpp binaries (CUDA / CPU)
- Speech models (ASR large-v3-turbo, VAD Silero)
- Speaker diarization models (pyannote-3-0, wespeaker CAM++)
- Ollama runtime and default LLM model (qwen3.5:9b)
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

from .config import Settings, discover_asr_backends, host_arch, is_apple_silicon

logger = logging.getLogger("not3.setup")

# Model URLs
WHISPER_RELEASES_API = "https://api.github.com/repos/ggml-org/whisper.cpp/releases?per_page=10"
HF_WHISPER_BASE = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
HF_VAD_URL = "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin"

DIARIZE_MODELS = {
    "sherpa-onnx-pyannote-segmentation-3-0.onnx": (
        "https://huggingface.co/csukuangfj/sherpa-onnx-pyannote-segmentation-3-0/resolve/main/model.onnx",
        "Pyannote segmentation 3.0 ONNX (~6 MB)",
    ),
    "wespeaker_en_voxceleb_CAM++_LM.onnx": (
        "https://huggingface.co/csukuangfj/speaker-embedding-models/resolve/main/wespeaker_en_voxceleb_CAM%2B%2B_LM.onnx",
        "WeSpeaker CAM++ speaker embedding ONNX (~29 MB)",
    ),
}

OLLAMA_SETUP_URL = "https://ollama.com/download/OllamaSetup.exe"


def has_nvidia() -> bool:
    return shutil.which("nvidia-smi") is not None and (
        subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0
    )


def is_ollama_installed() -> bool:
    if shutil.which("ollama"):
        return True
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        candidate = Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.is_file():
            return True
    return False


@dataclass
class SetupProgress:
    stage: str = "idle"  # idle | whisper | vad | asr | diarize | ollama | llm | complete | error
    item: str = ""
    percent: float = 0.0
    bytes_done: int = 0
    bytes_total: int = 0
    message: str = ""
    error: str | None = None
    is_running: bool = False


class SetupManager:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.load()
        self._current_progress = SetupProgress()
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._lock = asyncio.Lock()

    def _find_any_existing_asr_model(self) -> Path | None:
        """Find any verified Whisper speech model already downloaded."""
        primary = self.settings.asr_model_path()
        if primary.is_file() and primary.stat().st_size > 10_000_000:
            return primary

        # Check for any valid ggml whisper model in search dirs
        candidate_dirs = [
            self.settings.models_dir,
            self.settings.data_dir / "models",
            self.settings.repo_root / "models",
        ]
        for cdir in candidate_dirs:
            if cdir.is_dir():
                for f in cdir.glob("ggml-*.bin"):
                    fname = f.name.lower()
                    if "vad" not in fname and "silero" not in fname and f.stat().st_size > 10_000_000:
                        # Adopt existing model to prevent duplicate multi-GB download
                        self.settings.asr_model = f.name
                        return f
        return None

    def get_status(self) -> dict[str, Any]:
        s = self.settings
        backends = discover_asr_backends(s.repo_root)
        whisper_installed = len(backends) > 0

        existing_asr = self._find_any_existing_asr_model()
        asr_present = existing_asr is not None and existing_asr.stat().st_size > 10_000_000
        asr_model_name = existing_asr.name if existing_asr else s.asr_model

        vad_path = s.vad_model_path()
        vad_present = vad_path.is_file() and vad_path.stat().st_size > 500_000

        seg_path = s.diarize_segmentation_path()
        emb_path = s.diarize_embedding_path()
        seg_present = seg_path.is_file() and seg_path.stat().st_size > 1_000_000
        emb_present = emb_path.is_file() and emb_path.stat().st_size > 1_000_000
        diarize_present = seg_present and emb_present

        ollama_client = s.llm_client()
        ollama_installed = is_ollama_installed()
        ollama_running = ollama_client.available()
        ollama_models = ollama_client.models() if ollama_running else []
        default_model = s.model_distill or "qwen3.5:9b"
        model_present = any(
            m == default_model or m.startswith(f"{default_model}:") or
            any(prefix in m.lower() for prefix in ["qwen", "llama", "mistral", "gemma", "phi"])
            for m in ollama_models
        )

        all_ready = whisper_installed and asr_present and vad_present and diarize_present and ollama_running and model_present

        return {
            "ready": all_ready,
            "whisper": {
                "installed": whisper_installed,
                "backends": [b.name for b in backends],
            },
            "speech_models": {
                "asr_model": asr_model_name,
                "asr_present": asr_present,
                "vad_model": s.vad_model,
                "vad_present": vad_present,
            },
            "diarizer": {
                "installed": diarize_present,
                "segmentation_present": seg_present,
                "embedding_present": emb_present,
            },
            "ollama": {
                "installed": ollama_installed,
                "running": ollama_running,
                "url": s.ollama_url,
                "default_model": default_model,
                "model_present": model_present,
                "models": ollama_models,
            },
            "progress": asdict(self._current_progress),
        }

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.append(queue)
        # Yield initial status immediately
        await queue.put(asdict(self._current_progress))
        try:
            while True:
                data = await queue.get()
                yield data
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def _broadcast(self, progress: SetupProgress) -> None:
        self._current_progress = progress
        payload = asdict(progress)
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def start_setup(self, install_ollama: bool = True, pull_llm: bool = True) -> bool:
        if self._lock.locked():
            return False

        async with self._lock:
            try:
                self._broadcast(SetupProgress(
                    stage="starting",
                    message="Verifying existing components...",
                    is_running=True,
                ))

                # Step 1: Whisper CLI backend if missing
                backends = discover_asr_backends(self.settings.repo_root)
                if backends:
                    self._broadcast(SetupProgress(
                        stage="whisper",
                        item=f"whisper.cpp ({backends[0].name})",
                        percent=100.0,
                        message=f"Whisper engine verified ({backends[0].name}) — skipped reinstall.",
                        is_running=True,
                    ))
                else:
                    await self._install_whisper_backend()

                # Step 2: VAD model if missing
                vad_path = self.settings.vad_model_path()
                if vad_path.is_file() and vad_path.stat().st_size > 500_000:
                    self._broadcast(SetupProgress(
                        stage="vad",
                        item="Silero VAD model",
                        percent=100.0,
                        message="Silero VAD model verified — skipped download.",
                        is_running=True,
                    ))
                else:
                    await self._download_vad_model()

                # Step 3: Diarization models if missing
                seg_ok = self.settings.diarize_segmentation_path().is_file() and self.settings.diarize_segmentation_path().stat().st_size > 1_000_000
                emb_ok = self.settings.diarize_embedding_path().is_file() and self.settings.diarize_embedding_path().stat().st_size > 1_000_000
                if seg_ok and emb_ok:
                    self._broadcast(SetupProgress(
                        stage="diarize",
                        item="Diarization models",
                        percent=100.0,
                        message="Speaker diarization models verified — skipped download.",
                        is_running=True,
                    ))
                else:
                    await self._download_diarize_models()

                # Step 4: ASR model if missing
                asr_path = self._find_any_existing_asr_model()
                if asr_path is not None:
                    self._broadcast(SetupProgress(
                        stage="asr",
                        item=f"Whisper {asr_path.name}",
                        percent=100.0,
                        message=f"Speech model verified ({asr_path.name}) — skipped download.",
                        is_running=True,
                    ))
                else:
                    await self._download_asr_model()

                # Step 5: Ollama install / check
                if install_ollama:
                    await self._setup_ollama(pull_llm=pull_llm)

                self._broadcast(SetupProgress(
                    stage="complete",
                    percent=100.0,
                    message="All components verified and ready!",
                    is_running=False,
                ))
                return True
            except Exception as exc:
                logger.exception("Setup failed: %s", exc)
                self._broadcast(SetupProgress(
                    stage="error",
                    error=str(exc),
                    message=f"Setup failed: {exc}",
                    is_running=False,
                ))
                return False

    async def _download_file(
        self,
        url: str,
        dest: Path,
        stage: str,
        item: str,
        headers: dict[str, str] | None = None,
    ) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        hdrs = {"User-Agent": "not3-setup"}
        if headers:
            hdrs.update(headers)

        self._broadcast(SetupProgress(
            stage=stage,
            item=item,
            percent=0.0,
            message=f"Connecting to download {item}...",
            is_running=True,
        ))

        async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=hdrs) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length", 0))
                done = 0
                last_update = time.time()

                with tmp.open("wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 64):
                        f.write(chunk)
                        done += len(chunk)
                        now = time.time()
                        if now - last_update >= 0.25 or done == total:
                            last_update = now
                            pct = (done / total * 100) if total else 0.0
                            self._broadcast(SetupProgress(
                                stage=stage,
                                item=item,
                                percent=round(pct, 1),
                                bytes_done=done,
                                bytes_total=total,
                                message=f"Downloading {item}: {done / 1e6:.1f} / {total / 1e6:.1f} MB ({pct:.0f}%)",
                                is_running=True,
                            ))

        tmp.replace(dest)
        return dest

    async def _install_whisper_backend(self) -> None:
        arch = host_arch()
        use_cuda = sys.platform == "win32" and has_nvidia()
        backend_name = "cuda" if use_cuda else "cpu"
        dest_dir = self.settings.data_dir / "vendor" / "whisper" / f"{backend_name}-{arch}"
        dest_dir.mkdir(parents=True, exist_ok=True)

        self._broadcast(SetupProgress(
            stage="whisper",
            item="whisper.cpp engine",
            message=f"Looking up prebuilt whisper.cpp ({backend_name}) release...",
            is_running=True,
        ))

        # Determine download URL
        asset_name = "whisper-cublas-12.4.0-bin-x64.zip" if use_cuda else "whisper-bin-x64.zip"
        if sys.platform != "win32":
            asset_name = "whisper-bin-ubuntu-x64.tar.gz"

        download_url: str | None = None
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.get(WHISPER_RELEASES_API, headers={"User-Agent": "not3-setup"})
                if res.status_code == 200:
                    releases = res.json()
                    for rel in releases:
                        for asset in rel.get("assets", []):
                            if asset.get("name") == asset_name:
                                download_url = asset.get("browser_download_url")
                                break
                        if download_url:
                            break
        except Exception as e:
            logger.warning("Failed to query GitHub release API: %s", e)

        if not download_url:
            # Fallback to known tested release build
            download_url = f"https://github.com/ggml-org/whisper.cpp/releases/download/b5130/{asset_name}"

        zip_tmp = dest_dir / asset_name
        await self._download_file(download_url, zip_tmp, "whisper", f"whisper.cpp ({backend_name})")

        self._broadcast(SetupProgress(
            stage="whisper",
            item="whisper.cpp engine",
            percent=95.0,
            message=f"Extracting {asset_name}...",
            is_running=True,
        ))

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._extract_archive, zip_tmp, dest_dir)
        try:
            zip_tmp.unlink()
        except OSError:
            pass

    def _extract_archive(self, archive: Path, dest_dir: Path) -> None:
        exe_name = "whisper-cli.exe" if sys.platform == "win32" else "whisper-cli"
        staging = dest_dir.parent / f".staging-{dest_dir.name}"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        try:
            if archive.suffix == ".zip":
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(staging)
            else:
                import tarfile
                with tarfile.open(archive, "r:*") as tf:
                    tf.extractall(staging)

            source = next((p.parent for p in staging.rglob(exe_name)), None)
            if source:
                for item in source.iterdir():
                    shutil.copy2(item, dest_dir / item.name)
            else:
                for item in staging.rglob("*"):
                    if item.is_file():
                        shutil.copy2(item, dest_dir / item.name)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    async def _download_vad_model(self) -> None:
        dest = self.settings.data_dir / "models" / self.settings.vad_model
        await self._download_file(
            HF_VAD_URL,
            dest,
            stage="vad",
            item="Silero VAD model (~1 MB)",
        )

    async def _download_asr_model(self) -> None:
        model_name = self.settings.asr_model
        url = f"{HF_WHISPER_BASE}/{model_name}"
        dest = self.settings.data_dir / "models" / model_name
        await self._download_file(
            url,
            dest,
            stage="asr",
            item=f"Whisper {model_name} (~1.6 GB)",
        )

    async def _download_diarize_models(self) -> None:
        for filename, (url, desc) in DIARIZE_MODELS.items():
            dest = self.settings.data_dir / "models" / "diarize" / filename
            if not dest.is_file():
                await self._download_file(url, dest, stage="diarize", item=desc)

    async def _setup_ollama(self, pull_llm: bool = True) -> None:
        client = self.settings.llm_client()
        if not client.available():
            if not is_ollama_installed():
                if sys.platform == "win32":
                    self._broadcast(SetupProgress(
                        stage="ollama",
                        item="Ollama Installer",
                        message="Downloading Ollama Windows installer...",
                        is_running=True,
                    ))
                    installer_path = self.settings.data_dir / "OllamaSetup.exe"
                    await self._download_file(
                        OLLAMA_SETUP_URL,
                        installer_path,
                        stage="ollama",
                        item="Ollama Installer (~400 MB)",
                    )
                    self._broadcast(SetupProgress(
                        stage="ollama",
                        item="Ollama Installer",
                        message="Installing Ollama silently...",
                        is_running=True,
                    ))
                    # Run silent installer
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: subprocess.run([str(installer_path), "/VERYSILENT"], check=False),
                    )
                    try:
                        installer_path.unlink()
                    except OSError:
                        pass
                else:
                    logger.warning("Automatic Ollama install not implemented for non-Windows.")

            # Try starting Ollama if not running
            if not client.available():
                self._broadcast(SetupProgress(
                    stage="ollama",
                    item="Ollama Service",
                    message="Starting Ollama server...",
                    is_running=True,
                ))
                ollama_exe = shutil.which("ollama")
                if not ollama_exe and sys.platform == "win32":
                    cand = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
                    if cand.is_file():
                        ollama_exe = str(cand)

                if ollama_exe:
                    subprocess.Popen(
                        [ollama_exe, "serve"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=0x08000000 if sys.platform == "win32" else 0,
                    )
                    for _ in range(10):
                        await asyncio.sleep(1.0)
                        if client.available():
                            break

        # Pull default model if requested and running
        if pull_llm and client.available():
            default_model = self.settings.model_distill or "qwen3.5:9b"
            existing = client.models()
            matched = next(
                (
                    m for m in existing
                    if m == default_model or m.startswith(f"{default_model}:") or
                    any(p in m.lower() for p in ["qwen", "llama", "mistral", "gemma", "phi"])
                ),
                None,
            )
            if matched:
                self._broadcast(SetupProgress(
                    stage="llm",
                    item=f"Model: {matched}",
                    percent=100.0,
                    message=f"LLM model verified ({matched}) — skipped download.",
                    is_running=True,
                ))
                return

            self._broadcast(SetupProgress(
                stage="llm",
                item=f"Model: {default_model}",
                message=f"Pulling {default_model} through Ollama...",
                is_running=True,
            ))
            async with httpx.AsyncClient(timeout=1800.0) as http_client:
                async with http_client.stream(
                    "POST",
                    f"{self.settings.ollama_url}/api/pull",
                    json={"name": default_model, "stream": True},
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            total = data.get("total", 0)
                            completed = data.get("completed", 0)
                            status = data.get("status", "")
                            pct = (completed / total * 100) if total else 0.0
                            self._broadcast(SetupProgress(
                                stage="llm",
                                item=f"Model: {default_model}",
                                percent=round(pct, 1),
                                bytes_done=completed,
                                bytes_total=total,
                                message=f"{status} ({pct:.0f}%)" if total else status,
                                is_running=True,
                            ))
                        except Exception:
                            pass
