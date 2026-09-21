#!/usr/bin/env python3
"""Install whisper.cpp binaries and ggml models into the repo.

Windows and Linux get prebuilt binaries from the whisper.cpp release feed.
macOS has no prebuilt CLI in that feed, so this builds from source — which on
a Mac is cheap and gives you Metal, the whole reason Apple Silicon is worth
targeting. Everything lands in vendor/ and models/, both gitignored.

    python scripts/fetch_whisper.py                 # backend for this machine + turbo model
    python scripts/fetch_whisper.py --backend cpu   # force the CPU build
    python scripts/fetch_whisper.py --model large-v3-turbo-q5_0
    python scripts/fetch_whisper.py --list
"""

from __future__ import annotations

import argparse
import io
import json
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "whisper"
MODELS = ROOT / "models"

RELEASES = "https://api.github.com/repos/ggml-org/whisper.cpp/releases?per_page=20"
MODEL_BASE = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
VAD_URL = "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin"

# Asset name fragment per (platform, backend). macOS is absent on purpose:
# the release feed ships only an xcframework for Apple, not a CLI.
ASSETS = {
    ("win32", "cuda"): "whisper-cublas-12.4.0-bin-x64.zip",
    ("win32", "cpu"): "whisper-bin-x64.zip",
    ("linux", "cpu"): "whisper-bin-ubuntu-x64.tar.gz",
}

MODELS_AVAILABLE = [
    ("tiny", "75 MB", "fastest, rough"),
    ("base.en", "148 MB", "quick English drafts"),
    ("small", "488 MB", "decent, still fast on CPU"),
    ("large-v3-turbo-q5_0", "574 MB", "near-turbo quality, half the size"),
    ("large-v3-turbo", "1.6 GB", "recommended with a GPU"),
    ("large-v3", "3.1 GB", "best quality, slowest"),
]


def log(msg: str) -> None:
    print(msg, flush=True)


def arch() -> str:
    m = platform.machine().lower()
    return "arm64" if m in {"arm64", "aarch64"} else "x64"


def has_nvidia() -> bool:
    return shutil.which("nvidia-smi") is not None and (
        subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0
    )


def download(url: str, dest: Path | None = None) -> bytes | Path:
    """Fetch a URL, streaming to `dest` when given."""
    req = urllib.request.Request(url, headers={"User-Agent": "not3-fetch"})
    with urllib.request.urlopen(req, timeout=120) as r:
        total = int(r.headers.get("Content-Length") or 0)
        if dest is None:
            return r.read()
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        done = 0
        with tmp.open("wb") as fh:
            while block := r.read(1 << 20):
                fh.write(block)
                done += len(block)
                if total:
                    print(f"\r    {done / 1e6:7.0f} / {total / 1e6:.0f} MB"
                          f"  ({done / total:4.0%})", end="", flush=True)
        print()
        tmp.replace(dest)
        return dest


def latest_release_with_assets() -> dict:
    data = json.loads(download(RELEASES))
    for release in data:
        if release.get("assets"):
            return release
    raise SystemExit("No whisper.cpp release with binaries found.")


def install_binaries(backend: str) -> Path:
    key = (sys.platform, backend)
    if sys.platform == "darwin":
        return build_macos()
    if key not in ASSETS:
        raise SystemExit(
            f"No prebuilt whisper.cpp for {sys.platform}/{backend}. "
            "Build it yourself and put whisper-cli in "
            f"{VENDOR / f'{backend}-{arch()}'}."
        )

    release = latest_release_with_assets()
    wanted = ASSETS[key]
    asset = next((a for a in release["assets"] if a["name"] == wanted), None)
    if asset is None:
        raise SystemExit(f"Release {release['tag_name']} has no asset {wanted}")

    dest = VENDOR / f"{backend}-{arch()}"
    if (dest / _exe()).is_file():
        log(f"  {backend:6} already installed at {dest}")
        return dest

    log(f"  {backend:6} downloading {wanted} ({asset['size'] / 1e6:.0f} MB) "
        f"from {release['tag_name']}")
    blob = download(asset["browser_download_url"])

    staging = VENDOR / f".staging-{backend}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    if wanted.endswith(".zip"):
        zipfile.ZipFile(io.BytesIO(blob)).extractall(staging)
    else:
        tarfile.open(fileobj=io.BytesIO(blob)).extractall(staging)

    # Archives nest the binaries one level down (Release/ on Windows,
    # build/bin on Linux); flatten to whatever directory holds whisper-cli.
    source = next((p.parent for p in staging.rglob(_exe())), None)
    if source is None:
        raise SystemExit(f"{wanted} contained no {_exe()}")
    shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(dest))
    shutil.rmtree(staging, ignore_errors=True)
    log(f"  {backend:6} installed -> {dest}")
    return dest


def build_macos() -> Path:
    """Build whisper.cpp from source. Metal is on by default on Apple Silicon."""
    dest = VENDOR / f"macos-{arch()}"
    if (dest / _exe()).is_file():
        log(f"  macos  already installed at {dest}")
        return dest
    for tool in ("cmake", "git"):
        if shutil.which(tool) is None:
            raise SystemExit(
                f"{tool} is required to build whisper.cpp on macOS.\n"
                "  xcode-select --install && brew install cmake"
            )

    src = VENDOR / "src"
    if not (src / "CMakeLists.txt").is_file():
        log("  macos  cloning whisper.cpp")
        shutil.rmtree(src, ignore_errors=True)
        subprocess.run(
            ["git", "clone", "--depth", "1",
             "https://github.com/ggml-org/whisper.cpp", str(src)], check=True)

    log("  macos  building (Metal + CoreML where available)")
    build = src / "build"
    subprocess.run(
        ["cmake", "-B", str(build), "-S", str(src),
         "-DCMAKE_BUILD_TYPE=Release", "-DWHISPER_BUILD_TESTS=OFF"], check=True)
    subprocess.run(
        ["cmake", "--build", str(build), "--config", "Release", "-j"], check=True)

    binary = next((p for p in build.rglob(_exe()) if p.is_file()), None)
    if binary is None:
        raise SystemExit("Build finished but produced no whisper-cli.")
    dest.mkdir(parents=True, exist_ok=True)
    for item in binary.parent.iterdir():
        if item.is_file():
            shutil.copy2(item, dest / item.name)
    log(f"  macos  installed -> {dest}")
    return dest


def _exe() -> str:
    return "whisper-cli.exe" if sys.platform == "win32" else "whisper-cli"


def install_model(name: str) -> Path:
    dest = MODELS / f"ggml-{name}.bin"
    if dest.is_file():
        log(f"  model  {name} already present ({dest.stat().st_size / 1e6:.0f} MB)")
        return dest
    log(f"  model  downloading {name}")
    download(f"{MODEL_BASE}/ggml-{name}.bin", dest)
    log(f"  model  installed -> {dest}")
    return dest


def install_vad() -> Path:
    dest = MODELS / "ggml-silero-v5.1.2.bin"
    if not dest.is_file():
        log("  vad    downloading Silero VAD")
        download(VAD_URL, dest)
    return dest


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--backend", choices=["auto", "cuda", "cpu"], default="auto")
    p.add_argument("--model", default="large-v3-turbo")
    p.add_argument("--no-model", action="store_true", help="binaries only")
    p.add_argument("--list", action="store_true", help="list available models")
    args = p.parse_args()

    if args.list:
        print("models (pass with --model):\n")
        for name, size, note in MODELS_AVAILABLE:
            print(f"  {name:24} {size:>8}   {note}")
        return 0

    backend = args.backend
    if backend == "auto":
        if sys.platform == "darwin":
            backend = "metal"
        elif has_nvidia():
            backend = "cuda"
        else:
            backend = "cpu"

    log(f"platform {sys.platform}/{arch()}, backend {backend}")
    install_binaries("cpu" if backend == "metal" else backend)

    # On Windows the CUDA build is large; keep the CPU build too so there is
    # always a working fallback when a driver update breaks the GPU path.
    if backend == "cuda":
        try:
            install_binaries("cpu")
        except SystemExit as exc:
            log(f"  cpu    fallback unavailable: {exc}")

    if not args.no_model:
        install_model(args.model)
        install_vad()

    log("\ndone. check with:  cd engine && uv run not3 doctor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
