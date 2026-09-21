import { useCallback, useEffect, useMemo, useState } from "react";

import type { Lens, Note } from "./api";
import { restartEngine } from "./api";
import { NoteView } from "./components/NoteView";
import { Player } from "./components/Player";
import { Settings } from "./components/Settings";
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
  const [notesTick, setNotesTick] = useState(0);

  const { activeFor, tick, events } = useProgress(api);
  const data = useNoteData(api, selectedId, tick);

  const reloadNotes = useCallback(() => setNotesTick((t) => t + 1), []);
  const reloadLenses = useCallback(() => {
    void api?.lenses().then(setLenses).catch(() => undefined);
  }, [api]);

  useEffect(() => {
    if (!api) return;
    void api
      .notes()
      .then((list) => {
        setNotes(list);
        // Open something on first load so the window is never just empty.
        setSelectedId((current) => current ?? list[0]?.id ?? null);
      })
      .catch(() => undefined);
  }, [api, notesTick, tick]);

  useEffect(() => reloadLenses(), [reloadLenses]);

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
    // A note whose events all finished is no longer busy.
    for (const [noteId, stages] of events) {
      const last = [...stages.values()].at(-1);
      if (last && (last.type === "done" || last.type === "error")) busy.delete(noteId);
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
        selectedId={selectedId}
        busyNotes={busyNotes}
        onSelect={(id, seekMs) => {
          setSelectedId(id);
          if (seekMs != null) setPendingSeek(seekMs);
        }}
        onImported={reloadNotes}
        onOpenSettings={() => setShowSettings(true)}
        reload={reloadNotes}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1">
          <NoteView
            api={status.api}
            data={data}
            lenses={lenses}
            player={player}
            activeEvent={selectedId != null ? activeFor(selectedId) : null}
            onChanged={reloadNotes}
          />
        </div>
        <Player
          player={player}
          highlights={data.highlights}
          onScrubToHighlight={(h) => player.play(h.start_ms)}
        />
      </main>

      {showSettings && (
        <Settings
          api={status.api}
          lenses={lenses}
          onClose={() => setShowSettings(false)}
          onLensesChanged={reloadLenses}
          theme={theme.theme}
          onToggleTheme={theme.toggle}
        />
      )}
    </div>
  );
}
