#!/usr/bin/env python3
"""Build the Python engine into a standalone onedir distribution with PyInstaller.

Output is placed in `engine/dist/not3-engine/`, which Tauri includes via
`bundle.resources` so the desktop app requires no Python installation on the
user's system.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = ROOT / "engine"
NOT3_PKG = ENGINE_DIR / "not3"
DIST_DIR = ENGINE_DIR / "dist"
BUILD_DIR = ENGINE_DIR / "build"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build not3-engine with PyInstaller.")
    parser.add_argument("--clean", action="store_true", help="Clean build and dist directories first")
    args = parser.parse_args()

    if args.clean:
        if DIST_DIR.exists():
            shutil.rmtree(DIST_DIR)
        if BUILD_DIR.exists():
            shutil.rmtree(BUILD_DIR)

    entry_point = NOT3_PKG / "main.py"
    if not entry_point.is_file():
        print(f"Error: Entry point not found: {entry_point}", file=sys.stderr)
        return 1

    schema_sql = NOT3_PKG / "schema.sql"
    lenses_dir = NOT3_PKG / "lenses"
    sep = ";" if sys.platform == "win32" else ":"

    add_data = [
        f"{schema_sql}{sep}not3",
        f"{lenses_dir}{sep}not3/lenses",
    ]

    hidden_imports = [
        "not3",
        "not3.api",
        "not3.config",
        "not3.db",
        "not3.worker",
        "not3.pipeline",
        "not3.pipeline.ingest",
        "not3.pipeline.asr",
        "not3.pipeline.diarize",
        "not3.pipeline.distill",
        "not3.pipeline.highlight",
        "not3.pipeline.lens",
        "not3.pipeline.export",
        "not3.llm",
        "not3.llm.ollama",
        "not3.llm.chunker",
        "not3.llm.anchor",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "fastapi",
        "sse_starlette",
        "rapidfuzz",
        "numpy",
        "onnxruntime",
        "sherpa_onnx",
    ]

    cmd = [
        "uv", "run", "pyinstaller",
        "--noconfirm",
        "--onedir",
        "--name", "not3-engine",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        "--paths", str(ENGINE_DIR),
        "--collect-all", "onnxruntime",
        "--collect-all", "sherpa_onnx",
    ]

    for data in add_data:
        cmd.extend(["--add-data", data])

    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])

    cmd.append(str(entry_point))

    print(f"Building not3-engine for {platform.system()} {platform.machine()}...")
    print("Command:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=str(ENGINE_DIR))
    if res.returncode != 0:
        print("PyInstaller build failed!", file=sys.stderr)
        return res.returncode

    exe_name = "not3-engine.exe" if sys.platform == "win32" else "not3-engine"
    exe_path = DIST_DIR / "not3-engine" / exe_name
    if not exe_path.is_file():
        print(f"Error: Expected output binary not found at {exe_path}", file=sys.stderr)
        return 1

    print(f"\nSuccessfully built: {exe_path} ({exe_path.stat().st_size / 1e6:.1f} MB)")
    print("Testing binary with handshake check...")
    test_proc = subprocess.Popen(
        [str(exe_path), "--port", "0", "--watch-stdin"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        line = test_proc.stdout.readline()
        print(f"Handshake line received: {line.strip()}")
        import json
        data = json.loads(line)
        assert data.get("event") == "ready", f"Unexpected handshake: {data}"
        assert data.get("port") and data["port"] > 0, f"Invalid port: {data}"
        print(f"Verified engine ready on port {data['port']}, PID {data['pid']}!")
    finally:
        test_proc.terminate()
        test_proc.wait(timeout=5)

    print("Engine packaging complete and verified!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
