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

rem ----------------------------------------------------------- scoop path ---
rem  Scoop writes tool locations into the User PATH registry key, but the
rem  current shell session may pre-date that change.  Prepend the well-known
rem  Scoop app directories so that node, cargo, uv and ffmpeg are always
rem  visible without requiring the user to open a new terminal.

set "SCOOP_BASE=%USERPROFILE%\scoop\apps"
if exist "%SCOOP_BASE%\nodejs-lts\current\node.exe" (
  set "PATH=%SCOOP_BASE%\nodejs-lts\current\bin;%SCOOP_BASE%\nodejs-lts\current;%PATH%"
)
if exist "%SCOOP_BASE%\rust-msvc\current\bin\cargo.exe" (
  set "PATH=%SCOOP_BASE%\rust-msvc\current\bin;%PATH%"
)
rem uv and ffmpeg are shimmed through scoop\shims which is usually already on PATH.
if exist "%USERPROFILE%\scoop\shims\uv.exe" (
  set "PATH=%USERPROFILE%\scoop\shims;%PATH%"
)

rem ---------------------------------------------------------------- tools ---

set "MISSING="

where node >nul 2>&1
if errorlevel 1 (
  echo   [x] Node.js not found.
  set "MISSING=1"
)

where uv >nul 2>&1
if errorlevel 1 (
  echo   [x] uv not found.
  set "MISSING=1"
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo   [x] ffmpeg not found.
  set "MISSING=1"
)

if not "%MODE%"=="doctor" (
  where cargo >nul 2>&1
  if errorlevel 1 (
    echo   [x] Rust not found.
    set "MISSING=1"
  )
)

if defined MISSING (
  echo.
  echo   Run install-prereqs.bat to install missing tools, then try again.
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
    echo   [x] Whisper setup failed.
    pause
    exit /b 1
  )
  echo   [*] Downloading speaker diarization models...
  echo.
  python scripts\fetch_diarize.py
  if errorlevel 1 (
    echo.
    echo   [x] Diarizer setup failed.
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
  echo   [*] Packaging Python engine with PyInstaller...
  echo.
  python scripts\build_engine.py
  if errorlevel 1 (
    echo.
    echo   [x] Engine packaging failed.
    pause
    exit /b 1
  )
  echo.
  echo   [*] Building Tauri release binary and NSIS installer...
  echo.
  rem -- Init MSVC env so link.exe can find Windows SDK libs (e.g. dbghelp.lib) --
  set "VCVARS="
  for /f "usebackq tokens=*" %%I in (`"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe" -products * -all -prerelease -property installationPath 2^>nul`) do (
    if exist "%%I\VC\Auxiliary\Build\vcvars64.bat" set "VCVARS=%%I\VC\Auxiliary\Build\vcvars64.bat"
  )
  if defined VCVARS (
    call "!VCVARS!" >nul
    echo   [ok] MSVC environment loaded
    echo.
  ) else (
    echo   [!] vcvars64.bat not found. link.exe may not find Windows SDK libs.
    echo.
  )
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
  echo   [ok] Built: app\src-tauri\target\release\Not3.exe
  echo   [ok] Installer: app\src-tauri\target\release\bundle\nsis\Not3_0.1.0_x64-setup.exe
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

