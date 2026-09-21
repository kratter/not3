import { useEffect, useState } from "react";
import type { Api, SetupEvent, SetupStatus } from "../api";
import { Button, Chip, Icon, ProgressBar, Spinner } from "./ui";

export function SetupModal({
  api,
  onClose,
  onComplete,
}: {
  api: Api;
  onClose: () => void;
  onComplete?: () => void;
}) {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [event, setEvent] = useState<SetupEvent | null>(null);
  const [starting, setStarting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api
      .setupStatus()
      .then((s) => {
        if (active) {
          setStatus(s);
          setEvent(s.progress);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          setLoading(false);
          setActionError(err instanceof Error ? err.message : String(err));
        }
      });

    const ac = new AbortController();
    api
      .streamSetupEvents((evt) => {
        if (!active) return;
        setEvent(evt);
        if (evt.stage === "complete") {
          api.setupStatus().then((s) => active && setStatus(s));
          onComplete?.();
        }
      }, ac.signal)
      .catch(() => undefined);

    return () => {
      active = false;
      ac.abort();
    };
  }, [api, onComplete]);

  async function handleStart() {
    setStarting(true);
    setActionError(null);
    try {
      const res = await api.startSetup({ install_ollama: true, pull_llm: true });
      if (!res.started) {
        setActionError("Setup could not start (it may already be running).");
      }
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setStarting(false);
    }
  }

  const isRunning = event?.is_running ?? false;
  const isComplete = event?.stage === "complete" || (status?.ready ?? false);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-xl flex-col rounded-xl border border-[var(--border)] bg-[var(--bg)] shadow-2xl">
        <header className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--accent-wash)] text-[var(--accent)]">
              <Icon name="settings" className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-[16px] font-semibold text-[var(--text)]">Component Setup & Repair</h2>
              <p className="text-[12px] text-[var(--text-faint)]">
                Local transcription and AI models required by Not3
              </p>
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={isRunning}>
            ✕
          </Button>
        </header>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {loading ? (
            <div className="flex h-32 items-center justify-center">
              <Spinner className="h-6 w-6 text-[var(--accent)]" />
            </div>
          ) : (
            <>
              {/* Smart Caching Info Box */}
              <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] p-3 text-[12px] text-[var(--text-faint)] leading-relaxed">
                <span className="font-medium text-[var(--text)]">⚡ Smart Caching & Efficiency:</span>{" "}
                Only missing components are downloaded (one sample of each type). Any component that is already installed or tested is automatically detected and skipped to save disk space and bandwidth.
              </div>

              <div className="space-y-3">
                {/* Whisper Engine */}
                <div className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-3.5">
                  <div>
                    <div className="text-[13px] font-medium text-[var(--text)]">Transcription Engine</div>
                    <div className="text-[12px] text-[var(--text-faint)]">
                      whisper.cpp high-performance CLI (CUDA / CPU)
                    </div>
                  </div>
                  {status?.whisper.installed ? (
                    <Chip tone="good">Installed & Verified ({status.whisper.backends.join(", ")})</Chip>
                  ) : (
                    <Chip tone="bad">Missing</Chip>
                  )}
                </div>

                {/* Speech Model */}
                <div className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-3.5">
                  <div>
                    <div className="text-[13px] font-medium text-[var(--text)]">Speech Recognition Model</div>
                    <div className="text-[12px] text-[var(--text-faint)]">
                      {status?.speech_models.asr_model} & Silero VAD
                    </div>
                  </div>
                  {status?.speech_models.asr_present && status?.speech_models.vad_present ? (
                    <Chip tone="good">Installed & Verified</Chip>
                  ) : (
                    <Chip tone="bad">Missing</Chip>
                  )}
                </div>

                {/* Diarization */}
                <div className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-3.5">
                  <div>
                    <div className="text-[13px] font-medium text-[var(--text)]">Speaker Diarization</div>
                    <div className="text-[12px] text-[var(--text-faint)]">
                      Pyannote 3.0 + WeSpeaker CAM++ (~35 MB)
                    </div>
                  </div>
                  {status?.diarizer.installed ? (
                    <Chip tone="good">Installed & Verified</Chip>
                  ) : (
                    <Chip tone="bad">Missing</Chip>
                  )}
                </div>

                {/* Ollama & Model */}
                <div className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-3.5">
                  <div>
                    <div className="text-[13px] font-medium text-[var(--text)]">Ollama & Language Model</div>
                    <div className="text-[12px] text-[var(--text-faint)]">
                      Local AI runtime + {status?.ollama.models?.[0] || status?.ollama.default_model || "qwen3.5:9b"}
                    </div>
                  </div>
                  {status?.ollama.running && status?.ollama.model_present ? (
                    <Chip tone="good">Ready & Verified</Chip>
                  ) : status?.ollama.installed ? (
                    <Chip tone="warn">Model missing / Offline</Chip>
                  ) : (
                    <Chip tone="bad">Not Installed</Chip>
                  )}
                </div>
              </div>

              {/* Live progress box */}
              {isRunning && event && (
                <div className="space-y-2 rounded-lg border border-[var(--accent)]/30 bg-[var(--accent-wash)]/30 p-4">
                  <div className="flex items-center justify-between text-[13px]">
                    <span className="font-medium text-[var(--text)]">{event.message || "Downloading..."}</span>
                    <span className="text-[12px] font-mono text-[var(--accent)]">{event.percent}%</span>
                  </div>
                  <ProgressBar value={event.percent / 100} />
                  {event.item && (
                    <div className="text-[11px] text-[var(--text-faint)]">Target: {event.item}</div>
                  )}
                </div>
              )}

              {/* Error message */}
              {(actionError || event?.error) && (
                <div className="rounded-lg border border-[var(--bad)]/30 bg-[var(--bad)]/10 p-3 text-[12px] text-[var(--bad)]">
                  <div className="font-medium">Setup encountered an error:</div>
                  <div className="mt-1 font-mono">{actionError || event?.error}</div>
                </div>
              )}

              {/* Complete state */}
              {isComplete && !isRunning && (
                <div className="flex items-center gap-2 rounded-lg border border-[var(--good)]/30 bg-[var(--good)]/10 p-3 text-[13px] text-[var(--good)]">
                  <span className="text-base">✓</span>
                  <span>All components are downloaded, configured, and ready to use!</span>
                </div>
              )}
            </>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-[var(--border)] px-6 py-4">
          <Button variant="ghost" onClick={onClose} disabled={isRunning}>
            {isComplete ? "Done" : "Cancel"}
          </Button>

          {!isComplete && (
            <Button
              variant="solid"
              onClick={() => void handleStart()}
              disabled={loading || isRunning || starting}
            >
              {isRunning ? (
                <>
                  <Spinner className="mr-1 h-3.5 w-3.5" />
                  Setting up...
                </>
              ) : (
                "Download & Set Up Components"
              )}
            </Button>
          )}
        </footer>
      </div>
    </div>
  );
}
