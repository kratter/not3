"""M0: does faster-whisper actually run on this machine's GPU?

The open question is Blackwell (sm_120). CTranslate2 ships prebuilt CUDA kernels;
if it has no cubin for sm_120 and no forward-compatible PTX, CUDA init fails here
and the ASR backend has to fall back. Run this before building anything on top.
"""
import sys
import time

import ctranslate2
from faster_whisper import WhisperModel

AUDIO = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/jfk.wav"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "small"


def probe():
    print(f"ctranslate2        {ctranslate2.__version__}")
    try:
        count = ctranslate2.get_cuda_device_count()
    except Exception as exc:  # noqa: BLE001
        print(f"cuda device count  FAILED: {exc}")
        return 0
    print(f"cuda devices       {count}")
    print(f"cpu compute types  {sorted(ctranslate2.get_supported_compute_types('cpu'))}")
    if count:
        try:
            types = sorted(ctranslate2.get_supported_compute_types("cuda"))
            print(f"cuda compute types {types}")
        except Exception as exc:  # noqa: BLE001
            print(f"cuda compute types FAILED: {exc}")
            return 0
    return count


def run(device, compute_type):
    label = f"{device}/{compute_type}"
    try:
        t0 = time.perf_counter()
        model = WhisperModel(MODEL, device=device, compute_type=compute_type)
        load_s = time.perf_counter() - t0

        t0 = time.perf_counter()
        segments, info = model.transcribe(AUDIO, beam_size=5, vad_filter=True)
        segments = list(segments)
        infer_s = time.perf_counter() - t0
    except Exception as exc:  # noqa: BLE001
        print(f"\n{label:22} FAILED")
        print(f"  {type(exc).__name__}: {str(exc).strip()[:300]}")
        return None

    rtf = infer_s / info.duration if info.duration else float("nan")
    print(f"\n{label:22} OK")
    print(f"  load       {load_s:6.2f}s")
    print(f"  inference  {infer_s:6.2f}s for {info.duration:.1f}s audio  ->  {rtf:.3f}x realtime")
    print(f"  language   {info.language} ({info.language_probability:.2f})")
    for s in segments:
        print(f"  [{s.start:6.2f} -> {s.end:6.2f}]  {s.text.strip()}")
    return rtf


print(f"--- probe ---  model={MODEL}  audio={AUDIO}")
has_cuda = probe()

print("\n--- runs ---")
results = {}
if has_cuda:
    for ct in ("float16", "int8_float16"):
        rtf = run("cuda", ct)
        if rtf is not None:
            results[f"cuda/{ct}"] = rtf
            break
results["cpu/int8"] = run("cpu", "int8")

print("\n--- verdict ---")
best = [k for k, v in results.items() if v is not None]
if any(k.startswith("cuda") for k in best):
    print("CUDA works on sm_120. Plan holds: faster-whisper CUDA is the primary backend.")
else:
    print("CUDA unavailable. Fall back per plan: whisper.cpp CUDA -> Vulkan -> CPU int8.")
for k, v in results.items():
    print(f"  {k:22} {'FAILED' if v is None else f'{v:.3f}x realtime'}")
