@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

rem  install-prereqs.bat
rem  -------------------
rem  Checks for and installs all tools needed to build Not3 using Scoop.
rem
rem  Tools installed:
rem    Node.js LTS  -- Scoop package: nodejs-lts
rem    uv           -- Scoop package: uv
rem    FFmpeg       -- Scoop package: ffmpeg
rem    Rust/cargo   -- Scoop package: rust-msvc
rem
rem  Usage:
rem    install-prereqs.bat          install any missing tools
rem    install-prereqs.bat --check  report status only, no changes

title Not3 - Prerequisite Installer

set "CHECK_ONLY=0"
if /i "%~1"=="--check" set "CHECK_ONLY=1"

echo.
echo   Not3 Prerequisite Installer
echo   ----------------------------
echo.

rem ---------------------------------------------------------------- Scoop ---

where scoop >nul 2>&1
if not errorlevel 1 goto :scoop_ok

echo   [!] Scoop not found.
if "%CHECK_ONLY%"=="1" (
  echo       Scoop is required. Install it from https://scoop.sh
  echo.
  pause
  exit /b 1
)
echo   [*] Installing Scoop ...
powershell -ExecutionPolicy ByPass -NoProfile -Command "Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force; irm get.scoop.sh | iex"
if errorlevel 1 (
  echo   [x] Scoop install failed. Visit https://scoop.sh
  pause
  exit /b 1
)
set "PATH=%USERPROFILE%\scoop\shims;%PATH%"
echo   [ok] Scoop installed.
echo.

:scoop_ok
echo   [ok] Scoop
echo.

rem -- Refresh PATH so newly installed Scoop apps are visible this session --
set "PATH=%USERPROFILE%\scoop\apps\nodejs-lts\current\bin;%USERPROFILE%\scoop\apps\nodejs-lts\current;%USERPROFILE%\scoop\apps\rust-msvc\current\bin;%USERPROFILE%\scoop\shims;%PATH%"

rem ---------------------------------------------------------------- node ---

where node >nul 2>&1
if not errorlevel 1 (
  echo   [ok] Node.js
) else (
  if "%CHECK_ONLY%"=="1" (
    echo   [x] Node.js is NOT installed
    set "MISSING=1"
  ) else (
    echo   [*] Installing Node.js LTS ...
    scoop install nodejs-lts
    if errorlevel 1 ( echo   [x] Node.js install FAILED & set "FAILED=1" ) else (
      set "PATH=%USERPROFILE%\scoop\apps\nodejs-lts\current\bin;%USERPROFILE%\scoop\apps\nodejs-lts\current;%PATH%"
      echo   [ok] Node.js installed.
    )
  )
)

rem ------------------------------------------------------------------ uv ---

where uv >nul 2>&1
if not errorlevel 1 (
  echo   [ok] uv
) else (
  if "%CHECK_ONLY%"=="1" (
    echo   [x] uv is NOT installed
    set "MISSING=1"
  ) else (
    echo   [*] Installing uv ...
    scoop install uv
    if errorlevel 1 ( echo   [x] uv install FAILED & set "FAILED=1" ) else (
      echo   [ok] uv installed.
    )
  )
)

rem --------------------------------------------------------------- ffmpeg ---

where ffmpeg >nul 2>&1
if not errorlevel 1 (
  echo   [ok] FFmpeg
) else (
  if "%CHECK_ONLY%"=="1" (
    echo   [x] FFmpeg is NOT installed
    set "MISSING=1"
  ) else (
    echo   [*] Installing FFmpeg ...
    scoop install ffmpeg
    if errorlevel 1 ( echo   [x] FFmpeg install FAILED & set "FAILED=1" ) else (
      echo   [ok] FFmpeg installed.
    )
  )
)

rem --------------------------------------------------------------- cargo ---

where cargo >nul 2>&1
if not errorlevel 1 (
  echo   [ok] Rust / cargo
) else (
  if "%CHECK_ONLY%"=="1" (
    echo   [x] Rust / cargo is NOT installed
    set "MISSING=1"
  ) else (
    echo   [*] Installing Rust MSVC toolchain ...
    scoop install rust-msvc
    if errorlevel 1 ( echo   [x] Rust install FAILED & set "FAILED=1" ) else (
      set "PATH=%USERPROFILE%\scoop\apps\rust-msvc\current\bin;%PATH%"
      echo   [ok] Rust installed.
    )
  )
)

rem ---------------------------------------------------------- link.exe / MSVC ---
rem  Rust's MSVC toolchain needs cl.exe and link.exe from Visual C++ Build Tools.

set "LINK_FOUND=0"
for /f "tokens=*" %%D in ('dir /b /s "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\*\bin\Hostx64\x64\link.exe" 2^>nul') do set "LINK_FOUND=1"
for /f "tokens=*" %%D in ('dir /b /s "C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\*\bin\Hostx64\x64\link.exe" 2^>nul') do set "LINK_FOUND=1"

if "%LINK_FOUND%"=="1" (
  echo   [ok] MSVC C++ linker
) else (
  if "%CHECK_ONLY%"=="1" (
    echo   [x] MSVC C++ Build Tools NOT installed  ^(link.exe missing^)
    echo       Required by Rust to compile Tauri / WebView2
    set "MISSING=1"
  ) else (
    echo   [*] Installing Visual C++ Build Tools via winget...
    echo       ^(Large download ~3 GB, this will take 10-20 minutes^)
    winget install Microsoft.VisualStudio.2022.BuildTools --silent --accept-package-agreements --accept-source-agreements --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.Windows10SDK.22621 --includeRecommended"
    if errorlevel 1 ( echo   [x] VS Build Tools install FAILED & set "FAILED=1" ) else (
      echo   [ok] MSVC C++ Build Tools installed.
    )
  )
)


echo.
if defined FAILED (
  echo   [x] One or more installs failed. Check output above.
  echo.
  pause
  exit /b 1
)
if defined MISSING (
  echo   Some tools are missing.
  echo   Run install-prereqs.bat without --check to install them.
  echo.
  pause
  exit /b 1
)

echo   All prerequisites are present.
if "%CHECK_ONLY%"=="0" (
  echo   You can now run:  not3.bat build
)
echo.
pause
exit /b 0
