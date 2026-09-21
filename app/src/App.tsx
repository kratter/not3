import { useCallback, useEffect, useMemo, useState } from "react";

import type { Lens, Note } from "./api";
import { restartEngine } from "./api";
import { InsightsHub } from "./components/InsightsHub";
import { InteractiveTour } from "./components/InteractiveTour";
import { LockScreen } from "./components/LockScreen";
import { NoteView } from "./components/NoteView";
import { Player } from "./components/Player";
import { Settings } from "./components/Settings";
import { SetupModal } from "./components/SetupModal";
import { Sidebar } from "./components/Sidebar";
import { Button, Empty, Icon, Spinner } from "./components/ui";

import { useEngine, useNoteData, usePlayer, useProgress, useTheme } from "./hooks";

export default function App() {
  const { status, retry } = useEngine();
  const api = status.state === "ready" ? status.api : null;
  const theme = useTheme();

  const [notes, setNotes] = useState<Note[]>([]);
  const [lenses, setLenses] = useState<Lens[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [pendingSeek, setPendingSeek] = useState<number | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showSetup, setShowSetup] = useState(false);
  const [showTour, setShowTour] = useState(false);
  const [showInsights, setShowInsights] = useState(false);
  const [setupNeeded, setSetupNeeded] = useState(false);
  const [notesTick, setNotesTick] = useState(0);

  // App Security & Password Lock
  const [isLocked, setIsLocked] = useState(false);
  const [isPasswordProtected, setIsPasswordProtected] = useState(false);

  const checkAuth = useCallback(() => {
    if (!api) return;
    void api.authStatus().then((res) => {
      setIsPasswordProtected(res.password_required);
      if (res.password_required) {
        const unlocked = sessionStorage.getItem("not3_unlocked") === "true";
        setIsLocked(!unlocked);
      } else {
        setIsLocked(false);
      }
    }).catch(() => undefined);
  }, [api]);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const handleLock = useCallback(() => {
    sessionStorage.removeItem("not3_unlocked");
    setIsLocked(true);
  }, []);

  const handleUnlock = useCallback(() => {
    sessionStorage.setItem("not3_unlocked", "true");
    setIsLocked(false);
  }, []);


  const { activeFor, tick, events } = useProgress(api);
  const data = useNoteData(api, selectedId, tick);

  const reloadNotes = useCallback(() => setNotesTick((t) => t + 1), []);
  const reloadLenses = useCallback(() => {
    void api?.lenses().then(setLenses).catch(() => undefined);
  }, [api]);

  const handleDeleteNote = useCallback(async (id: number) => {
    if (!api) return;
    try {
      await api.remove(id);
      setSelectedId((current) => {
        if (current === id) {
          const remaining = notes.filter((n) => n.id !== id);
          return remaining[0]?.id ?? null;
        }
        return current;
      });
      reloadNotes();
    } catch (err) {
      console.error("Failed to delete note:", err);
    }
  }, [api, notes, reloadNotes]);

  useEffect(() => {
    if (!api) return;
    void api
      .notes()
      .then((list) => {
        setNotes(list);
        // Retain selection if the note still exists; otherwise switch to the first remaining note
        setSelectedId((current) => {
          if (current != null && list.some((n) => n.id === current)) return current;
          return list[0]?.id ?? null;
        });
      })
      .catch(() => undefined);
  }, [api, notesTick, tick]);

  useEffect(() => reloadLenses(), [reloadLenses]);

  useEffect(() => {
    if (!api) return;
    void api
      .setupStatus()
      .then((s) => {
        if (!s.ready) setSetupNeeded(true);
      })
      .catch(() => undefined);
  }, [api]);

  const note = data.detail?.note ?? null;
  const player = usePlayer(
    api && note?.media_path ? api.audioUrl(note.id) : null,
    note?.duration_ms ?? 0,
  );

  // A search result carries a timestamp; play it once the audio is loaded.
  useEffect(() => {
    if (pendingSeek == null || !note) return;
    const el = player.ref.current;
    if (!el) return;
    const go = () => {
      player.play(pendingSeek);
      setPendingSeek(null);
    };
    if (el.readyState >= 1) go();
    else el.addEventListener("loadedmetadata", go, { once: true });
  }, [pendingSeek, note, player]);

  const busyNotes = useMemo(() => {
    const busy = new Set<number>();
    for (const [noteId, stages] of events) {
      for (const event of stages.values()) {
        if (
          event.type === "progress" ||
          event.type === "queued" ||
          (event.type === "stage" && event.state === "running")
        ) {
          busy.add(noteId);
        }
      }
    }
    for (const n of notes) if (n.status === "processing") busy.add(n.id);
    // A note whose events all finished or was cancelled is no longer busy.
    for (const [noteId, stages] of events) {
      const allEvents = [...stages.values()];
      const last = allEvents.at(-1);
      const hasCancelled = allEvents.some((e) => e.type === "cancelled");
      if (hasCancelled || (last && (last.type === "done" || last.type === "error" || last.type === "cancelled"))) {
        busy.delete(noteId);
      }
    }
    return busy;
  }, [events, notes]);

  // Space toggles playback unless the user is typing.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (e.code === "Space") {
        e.preventDefault();
        player.toggle();
      } else if (e.key === "ArrowLeft" && e.shiftKey) {
        player.skip(-5000);
      } else if (e.key === "ArrowRight" && e.shiftKey) {
        player.skip(5000);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [player]);

  if (status.state === "connecting") {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-[var(--text-faint)]">
        <Spinner />
        <span className="text-[13px]">Starting the engine…</span>
      </div>
    );
  }

  if (status.state === "failed") {
    return (
      <div className="h-full">
        <Empty
          title="The engine isn't running"
          hint={status.error}
          action={
            <div className="flex gap-2">
              <Button
                variant="solid"
                onClick={() => void restartEngine().then(retry).catch(() => retry())}
              >
                <Icon name="refresh" className="h-3.5 w-3.5" />
                Restart it
              </Button>
              <Button variant="outline" onClick={() => void retry()}>
                Try again
              </Button>
            </div>
          }
        />
      </div>
    );
  }

  return (
    <div className="relative flex h-full">
      <Sidebar
        api={status.api}
        notes={notes}
        lenses={lenses}
        selectedId={selectedId}
        busyNotes={busyNotes}
        onSelect={(id, seekMs) => {
          setSelectedId(id);
          setShowInsights(false);
          if (seekMs != null) setPendingSeek(seekMs);
        }}
        onImported={reloadNotes}
        onOpenSettings={() => setShowSettings(true)}
        onOpenTour={() => setShowTour(true)}
        onOpenInsights={() => setShowInsights((v) => !v)}
        isInsightsOpen={showInsights}
        reload={reloadNotes}
        onLockApp={handleLock}
        isPasswordProtected={isPasswordProtected}
        onDeleteNote={handleDeleteNote}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        {setupNeeded && (
          <div className="flex items-center justify-between border-b border-[var(--warn)]/30 bg-[var(--warn)]/10 px-4 py-2 text-[12px] text-[var(--warn)]">
            <div className="flex items-center gap-2">
              <Icon name="alert" className="h-4 w-4 shrink-0" />
              <span>Some transcription or AI components are missing or not running.</span>
            </div>
            <Button
              variant="solid"
              size="sm"
              onClick={() => setShowSetup(true)}
              className="!bg-[var(--warn)] !text-black hover:!opacity-90 text-xs font-semibold"
            >
              Set Up Now
            </Button>
          </div>
        )}

        {showInsights ? (
          <div className="min-h-0 flex-1">
            <InsightsHub
              api={status.api}
              notes={notes}
              lenses={lenses}
              onSelectNote={(noteId, seekMs) => {
                setSelectedId(noteId);
                setShowInsights(false);
                if (seekMs != null) setPendingSeek(seekMs);
              }}
              onRefreshLibrary={() => {
                reloadNotes();
                reloadLenses();
              }}
              onClose={() => setShowInsights(false)}
            />
          </div>
        ) : (
          <>
            <div className="min-h-0 flex-1">
              <NoteView
                api={status.api}
                data={data}
                lenses={lenses}
                player={player}
                activeEvent={selectedId != null ? activeFor(selectedId) : null}
                onChanged={() => {
                  data.reload();
                  reloadNotes();
                }}
                onDeleteNote={handleDeleteNote}
              />
            </div>
            <Player
              player={player}
              highlights={data.highlights}
              onScrubToHighlight={(h) => player.play(h.start_ms)}
            />
          </>
        )}
      </main>

      {showSettings && (
        <Settings
          api={status.api}
          lenses={lenses}
          onClose={() => {
            setShowSettings(false);
            checkAuth();
          }}
          onLensesChanged={reloadLenses}
          theme={theme.theme}
          onToggleTheme={theme.toggle}
        />
      )}

      {showSetup && (
        <SetupModal
          api={status.api}
          onClose={() => setShowSetup(false)}
          onComplete={() => {
            setSetupNeeded(false);
            reloadNotes();
            reloadLenses();
          }}
        />
      )}

      <InteractiveTour
        isOpen={showTour}
        onClose={() => setShowTour(false)}
        onEnsureNoteSelected={() => {
          if (selectedId == null && notes.length > 0) {
            setSelectedId(notes[0]?.id ?? null);
          }
        }}
      />

      {isLocked && status.api && (
        <LockScreen api={status.api} onUnlocked={handleUnlock} />
      )}

    </div>
  );
}
