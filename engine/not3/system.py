"""Real-time system hardware and AI engine metrics."""

from __future__ import annotations

import platform
import shutil
import subprocess
import time
from typing import Any

import psutil

from .config import Settings

import threading

_last_metrics: dict[str, Any] = {}
_last_fetch_time: float = 0.0

_last_gpu_data: dict[str, Any] = {
    "available": False,
    "name": "No Dedicated GPU",
    "utilization": 0,
    "memory_used_mb": 0,
    "memory_total_mb": 0,
    "memory_percent": 0.0,
    "temperature": 0,
}
_last_gpu_time: float = 0.0
_gpu_lock = threading.Lock()
_nvidia_smi_path: str | None = shutil.which("nvidia-smi")


def _fetch_gpu_data() -> dict[str, Any]:
    global _last_gpu_data, _last_gpu_time
    now = time.time()
    if now - _last_gpu_time < 1.5:
        return _last_gpu_data

    # Use non-blocking acquire to avoid stalling requests if a query is slow
    if not _gpu_lock.acquire(blocking=False):
        return _last_gpu_data

    try:
        if _nvidia_smi_path:
            out = subprocess.check_output(
                [
                    _nvidia_smi_path,
                    "--query-gpu=name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=0.8,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000 if platform.system() == "Windows" else 0,
            ).strip()
            if out:
                parts = [p.strip() for p in out.split(",")]
                if len(parts) >= 6:
                    used_mb = int(parts[3])
                    total_mb = int(parts[4])
                    pct = round((used_mb / total_mb * 100) if total_mb > 0 else 0.0, 1)
                    _last_gpu_data = {
                        "available": True,
                        "name": parts[0],
                        "utilization": int(parts[1]),
                        "memory_used_mb": used_mb,
                        "memory_total_mb": total_mb,
                        "memory_percent": pct,
                        "temperature": int(parts[5]),
                    }
                    _last_gpu_time = now
    except Exception:
        pass
    finally:
        _gpu_lock.release()

    return _last_gpu_data


def get_system_metrics(
    settings: Settings, worker_status: dict[str, Any] | None = None
) -> dict[str, Any]:
    global _last_metrics, _last_fetch_time
    now = time.time()
    # Cache briefly for 0.8 seconds to avoid excess overhead
    if _last_metrics and (now - _last_fetch_time) < 0.8:
        return _last_metrics

    # 1. CPU & Memory
    cpu_pct = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()

    # 2. GPU
    if platform.system() == "Darwin" and platform.machine() in {"arm64", "aarch64"}:
        gpu_data = {
            "available": True,
            "name": "Apple Silicon (Metal)",
            "utilization": int(cpu_pct),
            "memory_used_mb": int((mem.total - mem.available) / (1024 * 1024)),
            "memory_total_mb": int(mem.total / (1024 * 1024)),
            "memory_percent": mem.percent,
            "temperature": 0,
        }
    else:
        gpu_data = _fetch_gpu_data()

    # 3. AI / Engine
    ws = worker_status or {}
    is_busy = ws.get("busy", False)
    ai_load = (
        max(gpu_data["utilization"], 85)
        if is_busy
        else (gpu_data["utilization"] if gpu_data["available"] else 0)
    )

    ai_data = {
        "busy": is_busy,
        "stage": ws.get("stage"),
        "note_id": ws.get("note_id"),
        "asr_backend": settings.asr_backend,
        "asr_model": settings.asr_model,
        "llm_model": settings.model_distill,
        "load_percent": ai_load,
    }

    result = {
        "timestamp": now,
        "cpu": {
            "percent": cpu_pct,
            "cores": psutil.cpu_count(logical=True) or 1,
        },
        "memory": {
            "percent": mem.percent,
            "used_gb": round((mem.total - mem.available) / (1024**3), 2),
            "total_gb": round(mem.total / (1024**3), 2),
        },
        "gpu": gpu_data,
        "ai": ai_data,
    }
    _last_metrics = result
    _last_fetch_time = now
    return result
