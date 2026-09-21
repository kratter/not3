@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

rem  Not3 launcher.
rem
rem    Not3.bat          start the app
rem    Not3.bat build    build a release binary into app\src-tauri\target\release
rem    Not3.bat doctor   check this machine without starting anything
rem    Not3.bat setup    download whisper.cpp binaries and models
rem
rem  Checks the things that actually go wrong before spending 30 seconds on a
rem  build that was going to fail anyway.

title Not3

set "MODE=%~1"
if "%MODE%"=="" set "MODE=run"

echo.
echo   Not3
echo   ----
echo.

rem ---------------------------------------------------------------- tools ---

set "MISSING="

where node >nul 2>&1
if errorlevel 1 (
  echo   [x] Node.js not found.
  echo       Install it from https://nodejs.org
  set "MISSING=1"
)

where uv >nul 2>&1
if errorlevel 1 (
  echo   [x] uv not found.
  echo       Install with:  winget install astral-sh.uv
  set "MISSING=1"
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo   [x] ffmpeg not found.
  echo       Install with:  winget install Gyan.FFmpeg
  set "MISSING=1"
)

if not "%MODE%"=="doctor" (
  where cargo >nul 2>&1
  if errorlevel 1 (
    echo   [x] Rust not found.
    echo       Install it from https://rustup.rs
    set "MISSING=1"
  )
)

if defined MISSING (
  echo.
  echo   Install what is marked above, then run this again.
  echo.
  pause
  exit /b 1
)

rem --------------------------------------------------------------- ollama ---

rem The engine calls Ollama for summaries, highlights and patterns. Without it
rem transcription still works, so this warns rather than stops.
call :check_ollama
if defined OLLAMA_UP (
  echo   [ok] Ollama running
) else (
  where ollama >nul 2>&1
  if errorlevel 1 (
    echo   [!] Ollama is not installed. Transcription will work; summaries,
    echo       highlights and patterns will not.
    echo       Get it from https://ollama.com
  ) else (
    echo   [*] Starting Ollama...
    start "" /b ollama serve >nul 2>&1
    call :wait_for_ollama
    if defined OLLAMA_UP (
      echo   [ok] Ollama running
    ) else (
      echo   [!] Ollama did not come up. Summaries and patterns will fail.
    )
  )
)
echo.

rem -------------------------------------------------------------- engine ----

if not exist "engine\.venv" (
  echo   [*] Setting up the Python engine, this takes a minute...
  pushd engine
  call uv sync
  if errorlevel 1 (
    echo   [x] uv sync failed.
    popd
    pause
    exit /b 1
  )
  popd
  echo   [ok] Engine ready
  echo.
)

if not exist "vendor\whisper" (
  echo   [!] No speech engine installed yet.
  echo       Run:  Not3.bat setup
  echo.
  if not "%MODE%"=="setup" (
    pause
    exit /b 1
  )
)

rem ---------------------------------------------------------------- modes ---

if /i "%MODE%"=="setup" (
  echo   [*] Downloading whisper.cpp and models, about 2 GB...
  echo.
  python scripts\fetch_whisper.py
  if errorlevel 1 (
    echo.
    echo   [x] Setup failed.
    pause
    exit /b 1
  )
  echo.
  echo   Done. Start the app with:  Not3.bat
  echo.
  pause
  exit /b 0
)

if /i "%MODE%"=="doctor" (
  pushd engine
  call uv run not3 doctor
  popd
  echo.
  pause
  exit /b 0
)

rem ------------------------------------------------------------- frontend ---

if not exist "app\node_modules" (
  echo   [*] Installing frontend packages, this takes a minute...
  pushd app
  call npm install
  if errorlevel 1 (
    echo   [x] npm install failed.
    popd
    pause
    exit /b 1
  )
  popd
  echo   [ok] Packages installed
  echo.
)

if /i "%MODE%"=="build" (
  echo   [*] Building a release binary. First build takes several minutes.
  echo.
  pushd app
  call npm run tauri build
  set "RC=!errorlevel!"
  popd
  if not "!RC!"=="0" (
    echo.
    echo   [x] Build failed.
    pause
    exit /b 1
  )
  echo.
  echo   Built: app\src-tauri\target\release\Not3.exe
  echo.
  pause
  exit /b 0
)

rem ------------------------------------------------------------------ run ---

echo   [*] Starting Not3. The first launch compiles Rust and takes a minute.
echo       Keep this window open while you use the app.
echo.

pushd app
call npm run tauri dev
set "RC=!errorlevel!"
popd

if not "%RC%"=="0" (
  echo.
  echo   [x] Not3 exited with code %RC%.
  echo.
  pause
  exit /b %RC%
)

exit /b 0

rem ------------------------------------------------------------ routines ---

:check_ollama
set "OLLAMA_UP="
curl -s -m 3 http://127.0.0.1:11434/api/version >nul 2>&1
if not errorlevel 1 set "OLLAMA_UP=1"
goto :eof

:wait_for_ollama
rem Confirm the server is actually answering rather than assuming it started.
for /l %%i in (1,1,12) do (
  ping -n 2 127.0.0.1 >nul
  call :check_ollama
  if defined OLLAMA_UP goto :eof
)
goto :eof

