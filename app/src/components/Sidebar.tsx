import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";

import type { Api, Note, SearchHit } from "../api";
import { cx, duration, relativeDate, ts } from "../util";
import { ManualNoteModal } from "./ManualNoteModal";
import { Button, Chip, Icon, Spinner } from "./ui";

const AUDIO_EXTENSIONS = [
  "mp3", "m4a", "wav", "flac", "ogg", "opus", "aac", "wma", "aiff",
  "mp4", "mkv", "mov", "webm", "avi", "m4v",
];

export function Sidebar({
  api, notes, selectedId, onSelect, onImported, onOpenSettings, busyNotes, reload,
}: {
  api: Api;
  notes: Note[];
  selectedId: number | null;
  onSelect: (id: number, seekMs?: number) => void;
  onImported: () => void;
  onOpenSettings: () => void;
  busyNotes: Set<number>;
  reload: () => void;
}) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [importing, setImporting] = useState(false);
  const [showWriteModal, setShowWriteModal] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Full-text search across every note, debounced so typing stays smooth.
  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) {
      setHits(null);
      return;
    }
    const timer = setTimeout(() => {
      void api.search(term).then(setHits).catch(() => setHits([]));
    }, 180);
    return () => clearTimeout(timer);
  }, [query, api]);

  async function pickFile() {
    setError(null);
    const picked = await open({
      multiple: false,
      filters: [{ name: "Audio or video", extensions: AUDIO_EXTENSIONS }],
    });
    if (typeof picked !== "string") return;
    setImporting(true);
    try {
      const { note_id, duplicate } = await api.importFile(picked);
      onSelect(note_id);
      onImported();
      if (duplicate) setError("Already in your library — opened the existing note.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setImporting(false);
    }
  }

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--bg-raised)]">
      <div className="flex items-center gap-2 px-3 py-3 select-none-ui">
        <span className="text-[15px] font-semibold tracking-tight">Not3</span>
        <div className="flex-1" />
        <Button onClick={onOpenSettings} title="Settings">
          <Icon name="settings" />
        </Button>
      </div>

      <div className="flex gap-2 px-3 pb-2">
        <Button variant="solid" onClick={() => void pickFile()} disabled={importing} className="flex-1">
          {importing ? <Spinner /> : <Icon name="plus" className="h-3.5 w-3.5" />}
          {importing ? "Importing…" : "Add recording"}
        </Button>
        <Button
          variant="outline"
          onClick={() => setShowWriteModal(true)}
          title="Write manual note or paste shorthand"
        >
          <Icon name="pencil" className="h-3.5 w-3.5" />
          Write
        </Button>
      </div>

      <div className="relative px-3 pb-2">
        <Icon
          name="search"
          className="pointer-events-none absolute left-5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-faint)]"
        />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search everything said"
          className="w-full rounded-md border border-[var(--border)] bg-[var(--bg-inset)] py-1.5 pl-7 pr-2 text-[13px] text-[var(--text)] placeholder:text-[var(--text-faint)] focus:border-[var(--accent)] focus:outline-none"
        />
      </div>

      {error && (
        <p className="mx-3 mb-2 rounded border border-[var(--border)] bg-[var(--bg-inset)] px-2 py-1.5 text-[11px] text-[var(--warn)]">
          {error}
        </p>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {hits !== null ? (
          <SearchResults hits={hits} onSelect={onSelect} />
        ) : notes.length === 0 ? (
          <p className="px-3 py-6 text-center text-[12px] leading-relaxed text-[var(--text-faint)]">
            No recordings yet.
            <br />
            Add one to get started.
          </p>
        ) : (
          notes.map((note) => (
            <NoteRow
              key={note.id}
              note={note}
              selected={note.id === selectedId}
              busy={busyNotes.has(note.id)}
              onSelect={() => onSelect(note.id)}
              onDelete={async () => {
                await api.remove(note.id);
                reload();
              }}
            />
          ))
        )}
      </div>

      <ManualNoteModal
        api={api}
        isOpen={showWriteModal}
        onClose={() => setShowWriteModal(false)}
        onCreated={(id) => {
          onSelect(id);
          onImported();
        }}
      />
    </aside>
  );
}

function NoteRow({
  note, selected, busy, onSelect, onDelete,
}: {
  note: Note;
  selected: boolean;
  busy: boolean;
  onSelect: () => void;
  onDelete: () => Promise<void>;
}) {
  const [confirming, setConfirming] = useState(false);

  return (
    <div
      onClick={onSelect}
      className={cx(
        "group mb-0.5 cursor-pointer rounded-md px-2.5 py-2 transition-colors",
        selected ? "bg-[var(--accent-wash)]" : "hover:bg-[var(--bg-inset)]",
      )}
    >
      <div className="flex items-start gap-2">
        <p
          className={cx(
            "min-w-0 flex-1 truncate text-[13px] font-medium leading-snug",
            selected ? "text-[var(--text)]" : "text-[var(--text-dim)]",
          )}
          title={note.title || note.source_name}
        >
          {note.title || note.source_name}
        </p>
        {busy && <Spinner className="mt-0.5 text-[var(--accent)]" />}
        {note.status === "error" && !busy && (
          <Icon name="alert" className="mt-0.5 h-3.5 w-3.5 text-[var(--bad)]" />
        )}
      </div>

      <div className="mt-1 flex items-center gap-2 text-[11px] text-[var(--text-faint)]">
        <span>{duration(note.duration_ms)}</span>
        <span>·</span>
        <span>{relativeDate(note.created_at)}</span>
        <div className="flex-1" />
        {confirming ? (
          <span className="flex items-center gap-1">
            <button
              type="button"
              className="text-[var(--bad)] hover:underline"
              onClick={(e) => {
                e.stopPropagation();
                void onDelete();
              }}
            >
              delete
            </button>
            <button
              type="button"
              className="hover:underline"
              onClick={(e) => {
                e.stopPropagation();
                setConfirming(false);
              }}
            >
              cancel
            </button>
          </span>
        ) : (
          <button
            type="button"
            title="Delete note"
            className="opacity-0 transition-opacity group-hover:opacity-100 hover:text-[var(--bad)]"
            onClick={(e) => {
              e.stopPropagation();
              setConfirming(true);
            }}
          >
            <Icon name="trash" className="h-3 w-3" />
          </button>
        )}
      </div>

      {(note.highlight_count || note.finding_count) ? (
        <div className="mt-1.5 flex gap-1">
          {!!note.highlight_count && (
            <Chip tone="accent">{note.highlight_count} highlights</Chip>
          )}
          {!!note.finding_count && <Chip>{note.finding_count} patterns</Chip>}
        </div>
      ) : null}
    </div>
  );
}

/** Render an FTS snippet. The engine delimits matches with U+0002/U+0003 rather
 *  than HTML, so nothing here has to trust or sanitise transcript text. */
function Snippet({ text }: { text: string }) {
  return (
    <>
      {text.split("\u0002").map((chunk, i) => {
        const [hit, ...rest] = chunk.split("\u0003");
        return i === 0 ? (
          <span key={i}>{chunk}</span>
        ) : (
          <span key={i}>
            <mark>{hit}</mark>
            {rest.join("")}
          </span>
        );
      })}
    </>
  );
}

function SearchResults({
  hits, onSelect,
}: {
  hits: SearchHit[];
  onSelect: (noteId: number, seekMs?: number) => void;
}) {
  if (hits.length === 0) {
    return (
      <p className="px-3 py-6 text-center text-[12px] text-[var(--text-faint)]">
        Nothing matched.
      </p>
    );
  }
  return (
    <>
      <p className="px-2.5 py-1.5 text-[11px] uppercase tracking-wide text-[var(--text-faint)]">
        {hits.length} {hits.length === 1 ? "result" : "results"}
      </p>
      {hits.map((hit) => (
        <button
          key={hit.id}
          type="button"
          onClick={() => onSelect(hit.note_id, hit.start_ms)}
          className="mb-0.5 block w-full rounded-md px-2.5 py-2 text-left hover:bg-[var(--bg-inset)]"
        >
          <p className="truncate text-[11px] text-[var(--text-faint)]">
            {hit.title || hit.source_name} · {ts(hit.start_ms)}
          </p>
          <p className="mt-0.5 text-[12px] leading-snug text-[var(--text-dim)]">
            <Snippet text={hit.snippet} />
          </p>
        </button>
      ))}
    </>
  );
}
