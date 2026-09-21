import { useEffect, useState } from "react";

import type { Api, Lens, ProgressEvent } from "../api";
import type { NoteData, Player as PlayerState } from "../hooks";
import { cx, duration } from "../util";
import { Highlights, Patterns } from "./Patterns";
import { Transcript } from "./Transcript";
import { Button, Chip, Empty, Icon, ProgressBar, Spinner, Tabs } from "./ui";

type TabId = "note" | "transcript" | "highlights" | "patterns";

const STAGE_LABELS: Record<string, string> = {
  ingest: "Import",
  transcribe: "Transcribe",
  diarize: "Speakers",
  distill: "Summarize",
  highlight: "Highlight",
  lens: "Patterns",
  embed: "Index",
  export: "Export",
};

export function NoteView({
  api, data, lenses, player, activeEvent, onChanged,
}: {
  api: Api;
  data: NoteData;
  lenses: Lens[];
  player: PlayerState;
  activeEvent: ProgressEvent | null;
  onChanged: () => void;
}) {
  const [tab, setTab] = useState<TabId>("note");
  const [focusSegment, setFocusSegment] = useState<number | null>(null);
  const [editingTitle, setEditingTitle] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");

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

  const running = data.jobs.filter((j) => j.state === "running");
  const failed = data.jobs.find((j) => j.state === "error");

  async function saveTitle() {
    setEditingTitle(false);
    const next = draftTitle.trim();
    if (next && next !== note!.title) {
      await api.rename(note!.id, next);
      onChanged();
    }
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
            <Chip tone={note.asr_backend === "cuda" ? "good" : "neutral"}>
              {note.asr_backend}
            </Chip>
          )}
          <div className="flex-1" />
          <Button
            size="sm"
            variant="outline"
            onClick={() => void api.run(note.id).then(onChanged)}
            disabled={running.length > 0}
            title="Re-run the whole pipeline for this note"
          >
            <Icon name="refresh" className="h-3 w-3" />
            Reprocess
          </Button>
          {running.length > 0 && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => void api.cancel(note.id).then(onChanged)}
            >
              Cancel
            </Button>
          )}
        </div>

        <StageStrip jobs={data.jobs} />

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

        {failed?.error && (
          <p className="mt-2 rounded border border-[var(--bad)]/30 bg-[var(--bad)]/8 px-2.5 py-1.5 text-[12px] text-[var(--bad)]">
            {STAGE_LABELS[failed.stage] ?? failed.stage} failed: {failed.error}
          </p>
        )}
      </header>

      <Tabs<TabId>
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "note", label: "Note" },
          { id: "transcript", label: "Transcript", count: data.segments.length },
          { id: "highlights", label: "Highlights", count: data.highlights.length },
          { id: "patterns", label: "Patterns", count: data.findings.length },
        ]}
      />

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
      </div>
    </div>
  );
}

function StageStrip({ jobs }: { jobs: NoteData["jobs"] }) {
  const shown = jobs.filter((j) => j.stage !== "embed" && j.stage !== "diarize");
  if (shown.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {shown.map((job) => {
        const tone =
          job.state === "done"
            ? "text-[var(--good)]"
            : job.state === "running"
              ? "text-[var(--accent)]"
              : job.state === "error"
                ? "text-[var(--bad)]"
                : "text-[var(--text-faint)]";
        return (
          <span
            key={job.stage}
            title={job.message ?? job.state}
            className={cx("flex items-center gap-1 text-[11px]", tone)}
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
            {STAGE_LABELS[job.stage] ?? job.stage}
          </span>
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
