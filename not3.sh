#!/usr/bin/env bash
#
# Not3 launcher for macOS and Linux. The Windows equivalent is Not3.bat.
#
#   ./not3.sh          start the app
#   ./not3.sh build    build a release binary
#   ./not3.sh doctor   check this machine without starting anything
#   ./not3.sh setup    build whisper.cpp and download models
#
set -uo pipefail
cd "$(dirname "$0")"

MODE="${1:-run}"

printf '\n  Not3\n  ----\n\n'

missing=0
need() {
    if ! command -v "$1" >/dev/null 2>&1; then
        printf '  [x] %s not found.\n      %s\n' "$1" "$2"
        missing=1
    fi
}

need node "Install from https://nodejs.org, or: brew install node"
need uv "Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
need ffmpeg "Install: brew install ffmpeg"
[ "$MODE" = "doctor" ] || need cargo "Install from https://rustup.rs"

if [ "$missing" -ne 0 ]; then
    printf '\n  Install what is marked above, then run this again.\n\n'
    exit 1
fi

# Ollama drives summaries, highlights and patterns. Transcription works without
# it, so this warns rather than stops.
if curl -s -m 3 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
    printf '  [ok] Ollama running\n'
elif command -v ollama >/dev/null 2>&1; then
    printf '  [*] Starting Ollama...\n'
    ollama serve >/dev/null 2>&1 &
    for _ in $(seq 1 12); do
        sleep 1
        if curl -s -m 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
            printf '  [ok] Ollama running\n'
            break
        fi
    done
else
    printf '  [!] Ollama is not installed. Transcription will work; summaries,\n'
    printf '      highlights and patterns will not. See https://ollama.com\n'
fi
printf '\n'

if [ ! -d engine/.venv ]; then
    printf '  [*] Setting up the Python engine, this takes a minute...\n'
    (cd engine && uv sync) || { printf '  [x] uv sync failed.\n'; exit 1; }
    printf '  [ok] Engine ready\n\n'
fi

case "$MODE" in
setup)
    # On macOS this compiles whisper.cpp so you get Metal; there is no
    # prebuilt CLI for Apple in the upstream release feed.
    printf '  [*] Installing whisper.cpp and models...\n\n'
    python3 scripts/fetch_whisper.py || { printf '\n  [x] Setup failed.\n'; exit 1; }
    printf '\n  Done. Start the app with:  ./not3.sh\n\n'
    exit 0
    ;;
doctor)
    (cd engine && uv run not3 doctor)
    exit $?
    ;;
esac

if [ ! -d vendor/whisper ]; then
    printf '  [!] No speech engine installed yet.\n      Run:  ./not3.sh setup\n\n'
    exit 1
fi

if [ ! -d app/node_modules ]; then
    printf '  [*] Installing frontend packages, this takes a minute...\n'
    (cd app && npm install) || { printf '  [x] npm install failed.\n'; exit 1; }
    printf '  [ok] Packages installed\n\n'
fi

if [ "$MODE" = "build" ]; then
    printf '  [*] Building a release binary. First build takes several minutes.\n\n'
    (cd app && npm run tauri build) || { printf '\n  [x] Build failed.\n'; exit 1; }
    printf '\n  Built into app/src-tauri/target/release\n\n'
    exit 0
fi

printf '  [*] Starting Not3. The first launch compiles Rust and takes a minute.\n'
printf '      Keep this terminal open while you use the app.\n\n'
cd app && exec npm run tauri dev
