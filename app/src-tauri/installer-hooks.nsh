; Custom NSIS Installer Hooks for Not3
; Prompts to install Ollama if not detected on the machine

!macro NSIS_HOOK_POSTINSTALL
  DetailPrint "Checking for Ollama installation..."

  ; Check LocalAppData standard installation path
  IfFileExists "$LOCALAPPDATA\Programs\Ollama\ollama.exe" ollama_found 0

  ; Ask user if they wish to install Ollama now
  MessageBox MB_YESNO|MB_ICONQUESTION \
    "Not3 uses Ollama for local AI summaries, highlights, and pattern analysis.$\r$\n$\r$\nOllama was not found on your system. Would you like to download and install Ollama now?" \
    IDNO skip_ollama

  DetailPrint "Downloading Ollama installer..."
  ; Use PowerShell to download Ollama installer into TEMP and run it
  nsExec::ExecToLog 'powershell -NoProfile -WindowStyle Hidden -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile(\"https://ollama.com/download/OllamaSetup.exe\", \"$TEMP\OllamaSetup.exe\"); Start-Process -FilePath \"$TEMP\OllamaSetup.exe\" -Wait"'

  Goto skip_ollama

ollama_found:
  DetailPrint "Ollama is already installed."

skip_ollama:
!macroend
