#!/usr/bin/env bash
# M0: measure every available whisper.cpp backend on the same audio, same model.
# Defaults are chosen from these numbers, not from assumption. Re-run on each
# target platform; this is also the Apple Silicon acceptance test.
set -u
MODEL="${1:-models/ggml-large-v3-turbo.bin}"
AUDIO="${2:-tests/fixtures/bench5m.wav}"
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$AUDIO")

echo "model  $MODEL"
echo "audio  $AUDIO  (${DUR}s)"
echo

for backend in cpu-x64 cuda-x64; do
    cli="vendor/whisper/$backend/whisper-cli.exe"
    [ -x "$cli" ] || { printf '%-10s not installed\n' "$backend"; continue; }
    start=$(date +%s.%N)
    "$cli" -m "$MODEL" -f "$AUDIO" -l auto -np -nt >/dev/null 2>&1
    rc=$?
    end=$(date +%s.%N)
    if [ $rc -ne 0 ]; then printf '%-10s FAILED (exit %d)\n' "$backend" "$rc"; continue; fi
    python -c "
e=$end-$start; d=$DUR
print(f'{\"$backend\":<10} {e:7.1f}s  ->  {e/d:6.3f}x realtime   (60 min audio ~ {60*e/d:5.1f} min)')"
done
