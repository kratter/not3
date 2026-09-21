import { useMemo, useState } from "react";

import type { Finding, Highlight, Lens } from "../api";
import type { Player } from "../hooks";
import { cx, humanize, ts } from "../util";
import { Chip, Confidence, Empty, Icon } from "./ui";

export function Highlights({
  highlights, player, onJump,
}: {
  highlights: Highlight[];
  player: Player;
  onJump: (segmentId: number) => void;
}) {
  if (highlights.length === 0) {
    return (
      <Empty
        title="No highlights yet"
        hint="Highlights are pulled out once the note has been processed."
      />
    );
  }
  return (
    <div className="h-full overflow-y-auto px-6 py-4">
      {highlights.map((h) => (
        <button
          key={h.id}
          type="button"
          onClick={() => {
            player.play(h.start_ms);
            onJump(h.segment_id);
          }}
          className="group mb-2 block w-full rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] p-3 text-left transition-colors hover:border-[var(--border-strong)]"
        >
          <div className="mb-1.5 flex items-center gap-2">
            <span className="font-mono text-[11px] tabular-nums text-[var(--accent)]">
              {ts(h.start_ms)}
            </span>
            <Icon
              name="play"
              className="h-2.5 w-2.5 text-[var(--text-faint)] opacity-0 transition-opacity group-hover:opacity-100"
            />
            <div className="flex-1" />
            {h.importance != null && <Confidence value={h.importance} />}
          </div>
          <p className="text-[14px] leading-relaxed text-[var(--text)]">
            &ldquo;{h.quote}&rdquo;
          </p>
          {h.reason && (
            <p className="mt-1.5 text-[12px] leading-snug text-[var(--text-faint)]">
              {h.reason}
            </p>
          )}
        </button>
      ))}
      <div className="h-24" />
    </div>
  );
}

export function Patterns({
  findings, lenses, durationMs, player, onJump,
}: {
  findings: Finding[];
  lenses: Lens[];
  durationMs: number;
  player: Player;
  onJump: (segmentId: number) => void;
}) {
  const [activeLens, setActiveLens] = useState<string | null>(null);

  const byLens = useMemo(() => {
    const map = new Map<string, Finding[]>();
    for (const f of findings) {
      const list = map.get(f.lens_id) ?? [];
      list.push(f);
      map.set(f.lens_id, list);
    }
    return map;
  }, [findings]);

  const lensById = useMemo(
    () => new Map(lenses.map((l) => [l.id, l])),
    [lenses],
  );

  if (findings.length === 0) {
    return (
      <Empty
        title="No patterns found"
        hint="Lenses run as part of processing. An empty result is a real result — it means nothing in this recording met the bar."
      />
    );
  }

  const visible = activeLens ? [activeLens] : [...byLens.keys()];

  return (
    <div className="h-full overflow-y-auto px-6 py-4">
      <p className="mb-4 rounded-md border border-[var(--border)] bg-[var(--bg-inset)] px-3 py-2 text-[12px] leading-relaxed text-[var(--text-faint)]">
        Each observation below is tied to a verbatim quote and a timestamp, so it
        can be checked against the recording. These describe language, not people
        — they are not a clinical or diagnostic assessment.
      </p>

      <div className="mb-4 flex flex-wrap gap-1.5">
        <button
          type="button"
          onClick={() => setActiveLens(null)}
          className={cx(
            "rounded-full px-2.5 py-1 text-[12px] transition-colors",
            activeLens === null
              ? "bg-[var(--accent-wash)] text-[var(--accent)]"
              : "text-[var(--text-faint)] hover:text-[var(--text-dim)]",
          )}
        >
          All {findings.length}
        </button>
        {[...byLens.entries()].map(([lensId, items]) => (
          <button
            key={lensId}
            type="button"
            onClick={() => setActiveLens(lensId === activeLens ? null : lensId)}
            className={cx(
              "rounded-full px-2.5 py-1 text-[12px] transition-colors",
              activeLens === lensId
                ? "bg-[var(--accent-wash)] text-[var(--accent)]"
                : "text-[var(--text-faint)] hover:text-[var(--text-dim)]",
            )}
          >
            {lensById.get(lensId)?.name ?? lensId} {items.length}
          </button>
        ))}
      </div>

      {visible.map((lensId) => {
        const items = byLens.get(lensId) ?? [];
        const lens = lensById.get(lensId);
        return (
          <section key={lensId} className="mb-6">
            <div className="mb-2 flex items-baseline gap-2">
              <h3 className="text-[13px] font-semibold text-[var(--text)]">
                {lens?.name ?? lensId}
              </h3>
              <span className="text-[11px] text-[var(--text-faint)]">
                {items.length} {items.length === 1 ? "observation" : "observations"}
              </span>
            </div>

            <Timeline
              items={items}
              durationMs={durationMs}
              currentMs={player.currentMs}
              onPick={(f) => {
                player.play(f.start_ms);
                onJump(f.segment_id);
              }}
            />

            <div className="mt-3">
              {items.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => {
                    player.play(f.start_ms);
                    onJump(f.segment_id);
                  }}
                  className="group mb-1.5 block w-full rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] p-3 text-left transition-colors hover:border-[var(--border-strong)]"
                >
                  <div className="mb-1.5 flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[11px] tabular-nums text-[var(--accent)]">
                      {ts(f.start_ms)}
                    </span>
                    <Chip tone="accent">{humanize(f.category)}</Chip>
                    <div className="flex-1" />
                    <Confidence value={f.confidence} />
                  </div>
                  <p className="text-[14px] leading-relaxed text-[var(--text)]">
                    &ldquo;{f.quote}&rdquo;
                  </p>
                  {f.rationale && (
                    <p className="mt-1.5 text-[12px] leading-snug text-[var(--text-faint)]">
                      {f.rationale}
                    </p>
                  )}
                </button>
              ))}
            </div>
          </section>
        );
      })}
      <div className="h-24" />
    </div>
  );
}

/**
 * Findings plotted against the recording.
 *
 * This is the view that makes an emotional arc legible as an arc rather than
 * a list: where the markers cluster, and what the conversation ends on.
 */
function Timeline({
  items, durationMs, currentMs, onPick,
}: {
  items: Finding[];
  durationMs: number;
  currentMs: number;
  onPick: (f: Finding) => void;
}) {
  if (durationMs <= 0) return null;
  const categories = [...new Set(items.map((i) => i.category))];

  return (
    <div className="relative h-9 rounded-md bg-[var(--bg-inset)]">
      {items.map((f) => {
        const left = Math.min(100, (f.start_ms / durationMs) * 100);
        const row = categories.indexOf(f.category);
        const top = 6 + (row % 3) * 9;
        return (
          <button
            key={f.id}
            type="button"
            title={`${ts(f.start_ms)} · ${humanize(f.category)} · ${Math.round(
              f.confidence * 100,
            )}%`}
            onClick={() => onPick(f)}
            className="absolute h-2 w-2 -translate-x-1/2 rounded-full transition-transform hover:scale-150"
            style={{
              left: `${left}%`,
              top,
              background: "var(--accent)",
              opacity: 0.35 + f.confidence * 0.65,
            }}
          />
        );
      })}
      <div
        className="pointer-events-none absolute inset-y-0 w-px bg-[var(--text)]"
        style={{ left: `${Math.min(100, (currentMs / durationMs) * 100)}%`, opacity: 0.5 }}
      />
    </div>
  );
}
