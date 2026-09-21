import { useEffect, useState } from "react";
import { revealItemInDir } from "@tauri-apps/plugin-opener";

import type { Api, Lens, NoteExport, ProgressEvent } from "../api";
import type { NoteData, Player as PlayerState } from "../hooks";
import { cx, duration } from "../util";
import { Highlights, Patterns } from "./Patterns";
import { ProcessOptionsModal } from "./ProcessOptionsModal";
import { Transcript } from "./Transcript";
import { Button, Chip, Empty, Icon, ProgressBar, Spinner, Tabs } from "./ui";
import { NoteChat } from "./NoteChat";
import { NoteComments } from "./NoteComments";
import { PlusNotes } from "./PlusNotes";

type TabId = "note" | "transcript" | "highlights" | "patterns" | "plus_notes" | "comments" | "ai_chat";


const STAGE_LABELS: Record<string, string> = {
  ingest: "Import",
  transcribe: "Transcribe",
  diarize: "Speakers",
  distill: "Summarize",
  highlight: "Highlight",
  lens: "Patterns",
  export: "Export",
};

export function NoteView({
  api, data, lenses, player, activeEvent, onChanged, onDeleteNote,
}: {
  api: Api;
  data: NoteData;
  lenses: Lens[];
  player: PlayerState;
  activeEvent: ProgressEvent | null;
  onChanged: () => void;
  onDeleteNote?: (id: number) => Promise<void> | void;
}) {
  const [tab, setTab] = useState<TabId>("note");
  const [focusSegment, setFocusSegment] = useState<number | null>(null);
  const [editingTitle, setEditingTitle] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  const [showReprocessModal, setShowReprocessModal] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportData, setExportData] = useState<NoteExport | null>(null);
  const [exporting, setExporting] = useState(false);
  const [copiedToast, setCopiedToast] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [actionInProgress, setActionInProgress] = useState(false);

  const note = data.detail?.note;

  useEffect(() => {
    setTab("note");
    setFocusSegment(null);
  }, [note?.id]);

  // Jumping to a quote from the highlights or patterns list should land on the
  // line in the transcript, not just move the playhead.
  function jumpToSegment(segmentId: number) {
    setTab("transcript");
    setFocusSegment(segmentId);
  }

  if (data.loading && !note) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="h-5 w-5 text-[var(--text-faint)]" />
      </div>
    );
  }
  if (data.error) {
    return <Empty title="Could not load this note" hint={data.error} />;
  }
  if (!note) {
    return (
      <Empty
        title="Nothing selected"
        hint="Pick a recording on the left, or add one to get started."
      />
    );
  }

  const running = data.jobs.filter((j) => j.state === "running" && j.stage !== "embed");
  const failed = data.jobs.find((j) => j.state === "error" && j.stage !== "embed");

  // Stages that are not yet done or errored (excluding embed and ingest)
  const pendingStages = data.jobs.filter(
    (j) => (j.state === "pending" || j.state === "error") && j.stage !== "embed" && j.stage !== "ingest"
  );
  const hasIncompleteStages =
    running.length === 0 &&
    pendingStages.length > 0 &&
    (data.segments.length > 0 || note?.asr_backend === "manual");

  async function saveTitle() {
    setEditingTitle(false);
    const next = draftTitle.trim();
    if (next && next !== note!.title) {
      await api.rename(note!.id, next);
      onChanged();
    }
  }

  async function handleExport() {
    if (!note) return;
    setExporting(true);
    try {
      const exp = await api.writeExport(note.id);
      setExportData(exp);
      setShowExportModal(true);
    } catch {
      const exp = await api.getExport(note.id);
      setExportData(exp);
      setShowExportModal(true);
    } finally {
      setExporting(false);
    }
  }

  async function handleCopyMarkdown() {
    if (!note) return;
    try {
      const exp = exportData ?? (await api.getExport(note.id));
      await navigator.clipboard.writeText(exp.content);
      setCopiedToast(true);
      setTimeout(() => setCopiedToast(false), 2500);
    } catch {
      /* ignore clipboard err */
    }
  }

  async function handleOpenExportFolder() {
    if (!note) return;
    if (exportData?.path) {
      void revealItemInDir(exportData.path);
    } else {
      const exp = await api.writeExport(note.id);
      setExportData(exp);
      void revealItemInDir(exp.path);
    }
  }

  async function handleContinue(skipDiarize = false) {
    if (!note || actionInProgress) return;
    setActionInProgress(true);
    try {
      let stagesToRun = pendingStages.map((j) => j.stage);
      if (skipDiarize) {
        stagesToRun = stagesToRun.filter((s) => s !== "diarize");
      }
      if (stagesToRun.length === 0) {
        stagesToRun = ["distill", "highlight", "lens", "export"];
      }
      await api.resetNote(note.id).catch(() => undefined);
      await api.run(note.id, { stages: stagesToRun });
      data.reload();
      onChanged();
    } finally {
      setActionInProgress(false);
    }
  }

  async function handleStartReprocess(opts: { style: string; lenses: string[] }) {
    if (!note || actionInProgress) return;
    setShowReprocessModal(false);
    setActionInProgress(true);
    try {
      if (running.length > 0) {
        await api.cancel(note.id).catch(() => undefined);
      }
      await api.resetNote(note.id).catch(() => undefined);
      await api.run(note.id, { lenses: opts.lenses, style: opts.style });
      data.reload();
      onChanged();
    } finally {
      setActionInProgress(false);
    }
  }

  async function handleCancel() {
    if (!note) return;
    await api.cancel(note.id);
    data.reload();
    onChanged();
  }

  return (
    <div className="flex h-full min-w-0 flex-col">
      <header className="border-b border-[var(--border)] px-6 pt-4 pb-3">
        {editingTitle ? (
          <input
            autoFocus
            value={draftTitle}
            onChange={(e) => setDraftTitle(e.target.value)}
            onBlur={() => void saveTitle()}
            onKeyDown={(e) => {
              if (e.key === "Enter") void saveTitle();
              if (e.key === "Escape") setEditingTitle(false);
            }}
            className="w-full rounded border border-[var(--accent)] bg-[var(--bg-inset)] px-2 py-1 text-[19px] font-semibold text-[var(--text)] focus:outline-none"
          />
        ) : (
          <h1
            onDoubleClick={() => {
              setDraftTitle(note.title || note.source_name);
              setEditingTitle(true);
            }}
            title="Double-click to rename"
            className="cursor-text text-[19px] font-semibold leading-tight tracking-tight"
          >
            {note.title || note.source_name}
          </h1>
        )}

        <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px] text-[var(--text-faint)]">
          <span>{duration(note.duration_ms)}</span>
          <span>·</span>
          <span className="truncate" title={note.source_path}>
            {note.source_name}
          </span>
          {note.language && (
            <>
              <span>·</span>
              <span className="uppercase">{note.language}</span>
            </>
          )}
          {note.asr_backend && (
            <Chip tone={note.asr_backend === "cuda" ? "good" : note.asr_backend === "manual" ? "accent" : "neutral"}>
              {note.asr_backend === "manual"
                ? note.asr_model === "formalized"
                  ? "formalized note"
                  : "manual note"
                : note.asr_backend}
            </Chip>
          )}
          <div className="flex-1" />
          <Button
            id="tour-export-btn"
            size="sm"
            variant="outline"
            onClick={() => void handleExport()}
            disabled={exporting}
            title="Export note to Markdown and view/open file"
          >
            <Icon name="export" className="h-3 w-3" />
            {exporting ? "Exporting..." : "Export"}
          </Button>
          <Button
            id="tour-reprocess-btn"
            size="sm"
            variant="outline"
            onClick={() => setShowReprocessModal(true)}
            disabled={actionInProgress}
            title="Re-run with custom lenses and report style"
          >
            <Icon name="refresh" className="h-3 w-3" />
            Reprocess
          </Button>
          {hasIncompleteStages && (
            <Button
              id="tour-continue-btn"
              size="sm"
              variant="solid"
              className="!bg-[var(--accent)] !text-white hover:opacity-90 shadow-sm"
              onClick={() => void handleContinue(false)}
              disabled={actionInProgress}
              title="Continue processing remaining stages"
            >
              ▶ Continue
            </Button>
          )}
          {running.length > 0 && (
            <Button
              size="sm"
              variant="outline"
              className="text-[var(--bad)] border-[var(--bad)]/40 hover:bg-[var(--bad)]/10"
              onClick={() => void handleCancel()}
              disabled={actionInProgress}
              title="Cancel ongoing or stuck processing"
            >
              Cancel
            </Button>
          )}
          {confirmDelete ? (
            <div className="flex items-center gap-1.5 rounded-md border border-[var(--bad)]/30 bg-[var(--bad)]/10 px-2 py-1">
              <span className="text-[11px] text-[var(--bad)] font-medium">Delete note?</span>
              <Button
                size="sm"
                variant="solid"
                className="h-6 text-[11px] !bg-[var(--bad)] !text-white hover:opacity-90"
                onClick={async () => {
                  setConfirmDelete(false);
                  if (onDeleteNote) {
                    await onDeleteNote(note.id);
                  } else {
                    await api.remove(note.id);
                    onChanged();
                  }
                }}
              >
                Yes, Delete
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-6 text-[11px]"
                onClick={() => setConfirmDelete(false)}
              >
                Cancel
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="outline"
              className="text-[var(--bad)] border-[var(--bad)]/30 hover:bg-[var(--bad)]/10"
              onClick={() => setConfirmDelete(true)}
              title="Delete this note and its recording"
            >
              <Icon name="trash" className="h-3 w-3" />
              Delete
            </Button>
          )}
        </div>

        <div id="tour-stage-strip">
          <StageStrip jobs={data.jobs} onExportClick={() => void handleExport()} />
        </div>

        {running.length > 0 && (
          <div className="mt-2">
            <ProgressBar
              value={
                activeEvent && activeEvent.type === "progress" ? activeEvent.progress : 0
              }
              label={
                activeEvent && "message" in activeEvent
                  ? activeEvent.message
                  : STAGE_LABELS[running[0]!.stage] ?? running[0]!.stage
              }
            />
          </div>
        )}

        {hasIncompleteStages && !failed && (
          <div className="mt-2.5 flex items-center justify-between rounded-lg border border-[var(--accent)]/40 bg-[var(--accent-wash)]/30 px-3 py-2 text-[12px]">
            <div className="flex items-center gap-2">
              <span className="flex h-2 w-2 rounded-full bg-[var(--accent)] animate-pulse" />
              <span className="text-[var(--text)]">
                <strong>Processing incomplete:</strong> {pendingStages.map((s) => STAGE_LABELS[s.stage] ?? s.stage).join(" → ")} pending.
              </span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {pendingStages.some((s) => s.stage === "diarize") && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-6 text-[11px]"
                  disabled={actionInProgress}
                  onClick={() => void handleContinue(true)}
                  title="Skip speaker diarization and proceed to AI summary immediately"
                >
                  Skip Diarize & Finish
                </Button>
              )}
              <Button
                size="sm"
                variant="solid"
                className="h-6 text-[11px] !bg-[var(--accent)] !text-white hover:opacity-90"
                disabled={actionInProgress}
                onClick={() => void handleContinue(false)}
                title="Continue all remaining unfinished stages"
              >
                ▶ Continue Processing
              </Button>
            </div>
          </div>
        )}

        {failed?.error && (
          <div className="mt-2 flex items-center justify-between rounded border border-[var(--bad)]/30 bg-[var(--bad)]/8 px-2.5 py-1.5 text-[12px] text-[var(--bad)]">
            <span className="truncate mr-2">
              <strong>{STAGE_LABELS[failed.stage] ?? failed.stage} failed:</strong> {failed.error}
            </span>
            <div className="flex items-center gap-1.5 shrink-0">
              <Button
                size="sm"
                variant="outline"
                className="h-6 text-[11px] border-[var(--bad)]/40 text-[var(--bad)] hover:bg-[var(--bad)]/15"
                onClick={async () => {
                  await api.resetNote(note.id);
                  data.reload();
                  onChanged();
                }}
                title="Reset note errors and restore clean state"
              >
                Reset
              </Button>
              {(data.segments.length > 0 || note.asr_backend === "manual") && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-6 text-[11px] border-[var(--accent)]/40 text-[var(--accent)] hover:bg-[var(--accent)]/15"
                  onClick={() => void handleContinue(false)}
                  title="Continue from where it left off"
                >
                  ▶ Continue
                </Button>
              )}
              <Button
                size="sm"
                variant="solid"
                className="h-6 text-[11px] !bg-[var(--bad)] !text-white hover:opacity-90"
                onClick={() => setShowReprocessModal(true)}
                title="Reprocess note with custom lenses and style"
              >
                <Icon name="refresh" className="mr-1 h-3 w-3" />
                Reprocess
              </Button>
            </div>
          </div>
        )}
      </header>

      <div id="tour-nav-tabs">
        <Tabs<TabId>
          value={tab}
          onChange={setTab}
          tabs={[
            { id: "note", label: "Note" },
            { id: "transcript", label: "Transcript", count: data.segments.length },
            { id: "highlights", label: "Highlights", count: data.highlights.length },
            { id: "patterns", label: "Patterns", count: data.findings.length },
            { id: "plus_notes", label: "Plus Notes", count: data.detail?.plus_notes ? 1 : undefined },
            { id: "comments", label: "Comments", count: data.detail?.comments?.length ?? 0 },
            { id: "ai_chat", label: "✨ AI Chat & Reformat" },
          ]}
        />
      </div>

      <div className="min-h-0 flex-1">
        {tab === "note" && (
          <NoteSummary sections={data.detail?.sections ?? {}} />
        )}
        {tab === "transcript" && (
          <Transcript
            segments={data.segments}
            speakers={data.detail?.speakers ?? []}
            highlights={data.highlights}
            player={player}
            focusSegmentId={focusSegment}
            onRenameSpeaker={async (speakerId, newName) => {
              await api.renameSpeaker(speakerId, newName);
              onChanged();
            }}
          />
        )}
        {tab === "highlights" && (
          <Highlights
            highlights={data.highlights}
            player={player}
            onJump={jumpToSegment}
          />
        )}
        {tab === "patterns" && (
          <Patterns
            findings={data.findings}
            lenses={lenses}
            durationMs={note.duration_ms}
            player={player}
            onJump={jumpToSegment}
          />
        )}
        {tab === "plus_notes" && (
          <PlusNotes
            api={api}
            noteId={note.id}
            initialContent={data.detail?.plus_notes ?? ""}
            onChanged={onChanged}
          />
        )}
        {tab === "comments" && (
          <NoteComments
            api={api}
            noteId={note.id}
            comments={data.detail?.comments ?? []}
            player={player}
            onCommentsChanged={onChanged}
          />
        )}
        {tab === "ai_chat" && (
          <NoteChat
            api={api}
            noteId={note.id}
            noteTitle={note.title || note.source_name}
            onSectionUpdated={() => onChanged()}
            onPlusNotesUpdated={() => onChanged()}
          />
        )}
      </div>


      {showReprocessModal && (
        <ProcessOptionsModal
          title="Reprocess Note"
          subtitle={note.title || note.source_name}
          lenses={lenses}
          onConfirm={handleStartReprocess}
          onClose={() => setShowReprocessModal(false)}
        />
      )}

      {showExportModal && exportData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-xl border border-[var(--border)] bg-[var(--bg)] shadow-2xl">
            <header className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
              <div>
                <h2 className="text-[16px] font-semibold text-[var(--text)]">Export Note</h2>
                <p className="truncate max-w-md text-[12px] text-[var(--text-faint)]">{exportData.filename}</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setShowExportModal(false)}>✕</Button>
            </header>

            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              <div className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-3">
                <div className="truncate mr-3">
                  <div className="text-[11px] font-semibold uppercase text-[var(--text-faint)]">Exported Path</div>
                  <div className="truncate font-mono text-[12px] text-[var(--text-dim)]">{exportData.path}</div>
                </div>
                <Button size="sm" variant="outline" onClick={() => void handleOpenExportFolder()}>
                  Open Folder ↗
                </Button>
              </div>

              <div>
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-[12px] font-semibold text-[var(--text-faint)] uppercase tracking-wider">Markdown Output</span>
                  {copiedToast ? (
                    <Chip tone="good">Copied to clipboard!</Chip>
                  ) : (
                    <Button size="sm" variant="ghost" onClick={() => void handleCopyMarkdown()} className="text-[12px] h-7">
                      Copy Markdown
                    </Button>
                  )}
                </div>
                <textarea
                  readOnly
                  value={exportData.content}
                  className="h-64 w-full font-mono text-[12px] rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] p-3 text-[var(--text)] focus:outline-none resize-none leading-relaxed"
                />
              </div>
            </div>

            <footer className="flex items-center justify-between border-t border-[var(--border)] px-6 py-4">
              <Button variant="outline" onClick={() => void handleCopyMarkdown()}>
                {copiedToast ? "Copied!" : "Copy to Clipboard"}
              </Button>
              <div className="flex gap-2">
                <Button variant="solid" onClick={() => void handleOpenExportFolder()}>
                  Show in Explorer
                </Button>
                <Button variant="ghost" onClick={() => setShowExportModal(false)}>
                  Done
                </Button>
              </div>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}

function StageStrip({
  jobs,
  onExportClick,
}: {
  jobs: NoteData["jobs"];
  onExportClick?: () => void;
}) {
  const shown = jobs.filter((j) => j.stage !== "embed");
  if (shown.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {shown.map((job) => {
        const isExport = job.stage === "export";
        const tone =
          job.state === "done"
            ? "text-[var(--good)]"
            : job.state === "running"
              ? "text-[var(--accent)]"
              : job.state === "error"
                ? "text-[var(--bad)]"
                : "text-[var(--text-faint)]";
        return (
          <button
            key={job.stage}
            type="button"
            onClick={isExport ? onExportClick : undefined}
            title={isExport ? "Click to export / open note" : (job.message ?? job.state)}
            className={cx(
              "flex items-center gap-1 text-[11px] rounded px-1 py-0.5 transition-colors",
              tone,
              isExport && "cursor-pointer hover:bg-[var(--bg-inset)] hover:underline",
            )}
          >
            <span
              className={cx(
                "h-1.5 w-1.5 rounded-full",
                job.state === "done" && "bg-[var(--good)]",
                job.state === "running" && "bg-[var(--accent)] pulse",
                job.state === "error" && "bg-[var(--bad)]",
                (job.state === "pending" || job.state === "skipped") &&
                  "bg-[var(--border-strong)]",
              )}
            />
            <span>{STAGE_LABELS[job.stage] ?? job.stage}</span>
            {isExport && <span className="text-[9px] opacity-70">↗</span>}
          </button>
        );
      })}
    </div>
  );
}

function NoteSummary({ sections }: { sections: Record<string, string> }) {
  const { summary, key_points, action_items, topics } = sections;
  if (!summary && !key_points && !action_items) {
    return (
      <Empty
        title="Not summarized yet"
        hint="The summary, key points and action items appear once processing finishes."
      />
    );
  }
  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      {summary && (
        <section className="mb-6">
          <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-faint)]">
            Summary
          </h2>
          <p className="max-w-3xl text-[14px] leading-relaxed text-[var(--text)]">
            {summary}
          </p>
        </section>
      )}
      {key_points && <Bullets title="Key points" body={key_points} />}
      {action_items && <Bullets title="Action items" body={action_items} accent />}
      {topics && (
        <section className="mb-6">
          <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-faint)]">
            Topics
          </h2>
          <div className="flex flex-wrap gap-1.5">
            {topics.split(",").map((t) => (
              <Chip key={t}>{t.trim()}</Chip>
            ))}
          </div>
        </section>
      )}
      <div className="h-24" />
    </div>
  );
}

function Bullets({ title, body, accent }: { title: string; body: string; accent?: boolean }) {
  const items = body
    .split("\n")
    .map((l) => l.replace(/^-\s*/, "").trim())
    .filter(Boolean);
  if (items.length === 0) return null;
  return (
    <section className="mb-6">
      <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-faint)]">
        {title}
      </h2>
      <ul className="max-w-3xl space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2 text-[14px] leading-relaxed text-[var(--text)]">
            <span
              className={cx(
                "mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full",
                accent ? "bg-[var(--accent)]" : "bg-[var(--border-strong)]",
              )}
            />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
