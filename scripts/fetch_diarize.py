#!/usr/bin/env python3
"""Download offline speaker diarization models for sherpa-onnx into models/diarize/.

Models downloaded:
1. pyannote-segmentation-3-0 (ONNX, ~5.9 MB)
2. wespeaker_en_voxceleb_CAM++_LM (ONNX, ~29.2 MB)

Both are public, zero-auth ONNX models running completely offline.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIARIZE_DIR = ROOT / "models" / "diarize"

MODELS = {
    "segmentation": {
        "filename": "sherpa-onnx-pyannote-segmentation-3-0.onnx",
        "url": "https://huggingface.co/csukuangfj/sherpa-onnx-pyannote-segmentation-3-0/resolve/main/model.onnx",
        "desc": "Pyannote segmentation 3.0 ONNX (~5.9 MB)",
    },
    "embedding": {
        "filename": "wespeaker_en_voxceleb_CAM++_LM.onnx",
        "url": "https://huggingface.co/csukuangfj/speaker-embedding-models/resolve/main/wespeaker_en_voxceleb_CAM%2B%2B_LM.onnx",
        "desc": "WeSpeaker VoxCeleb CAM++ speaker embedding ONNX (~29.2 MB)",
    },
}


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        print(f"  already present: {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        return dest

    print(f"  fetching {dest.name} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "not3-fetch"})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=120) as r:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with tmp.open("wb") as fh:
            while block := r.read(1 << 20):
                fh.write(block)
                done += len(block)
                if total:
                    print(f"\r    {done / 1e6:6.1f} / {total / 1e6:.1f} MB ({done / total:4.0%})", end="", flush=True)
        print()
    tmp.replace(dest)
    print(f"  saved: {dest.name}")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Download diarization models for Not3.")
    parser.add_argument("--dest", type=Path, default=DIARIZE_DIR, help="Destination directory")
    args = parser.parse_args()

    dest_dir = Path(args.dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading speaker diarization models to {dest_dir}:")

    for key, info in MODELS.items():
        print(f"\n[{key}] {info['desc']}")
        target = dest_dir / info["filename"]
        try:
            download(info["url"], target)
        except Exception as exc:
            print(f"Error downloading {key}: {exc}", file=sys.stderr)
            return 1

    print("\nAll diarization models ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
