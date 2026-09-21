import { useCallback, useRef } from "react";

import type { Highlight } from "../api";
import type { Player as PlayerState } from "../hooks";
import { ts } from "../util";
import { Button, Icon } from "./ui";

const RATES = [0.75, 1, 1.25, 1.5, 2];

export function Player({
  player, highlights, onScrubToHighlight,
}: {
  player: PlayerState;
  highlights: Highlight[];
  onScrubToHighlight: (h: Highlight) => void;
}) {
  const track = useRef<HTMLDivElement>(null);
  const total = player.durationMs || 1;

  const scrub = useCallback(
    (clientX: number) => {
      const rect = track.current?.getBoundingClientRect();
      if (!rect) return;
      const fraction = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      player.seek(fraction * total);
    },
    [player, total],
  );

  // Dragging continues outside the element, so listeners go on the window and
  // come off on release.
  const startDrag = useCallback(
    (e: React.MouseEvent) => {
      scrub(e.clientX);
      const move = (ev: MouseEvent) => scrub(ev.clientX);
      const up = () => {
        window.removeEventListener("mousemove", move);
        window.removeEventListener("mouseup", up);
      };
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup", up);
    },
    [scrub],
  );

  if (!player.src) return null;

  return (
    <div className="flex shrink-0 items-center gap-3 border-t border-[var(--border)] bg-[var(--bg-raised)] px-4 py-2.5 select-none-ui">
      <audio ref={player.ref} src={player.src} preload="metadata" />

      <Button onClick={() => player.skip(-10000)} title="Back 10 seconds">
        <Icon name="back" className="h-3.5 w-3.5" />
      </Button>
      <button
        type="button"
        onClick={player.toggle}
        title={player.playing ? "Pause (space)" : "Play (space)"}
        className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--accent)] text-white transition-colors hover:bg-[var(--accent-dim)]"
      >
        <Icon name={player.playing ? "pause" : "play"} className="h-3.5 w-3.5" />
      </button>
      <Button onClick={() => player.skip(10000)} title="Forward 10 seconds">
        <Icon name="forward" className="h-3.5 w-3.5" />
      </Button>

      <span className="w-14 text-right font-mono text-[11px] tabular-nums text-[var(--text-dim)]">
        {ts(player.currentMs)}
      </span>

      <div
        ref={track}
        onMouseDown={startDrag}
        className="group relative h-6 flex-1 cursor-pointer"
      >
        <div className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-[var(--bg-inset)]" />
        <div
          className="absolute top-1/2 left-0 h-1 -translate-y-1/2 rounded-full bg-[var(--accent)]"
          style={{ width: `${(player.currentMs / total) * 100}%` }}
        />

        {/* Highlights as marks on the scrubber: the shape of the recording at
            a glance, and a way to jump between its moments. */}
        {highlights.map((h) => (
          <button
            key={h.id}
            type="button"
            title={`${ts(h.start_ms)} — ${h.quote.slice(0, 80)}`}
            onMouseDown={(e) => {
              e.stopPropagation();
              onScrubToHighlight(h);
            }}
            className="absolute top-1/2 h-2.5 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--warn)] transition-all hover:h-4 hover:w-1"
            style={{ left: `${Math.min(100, (h.start_ms / total) * 100)}%` }}
          />
        ))}

        <div
          className="pointer-events-none absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--text)] opacity-0 shadow transition-opacity group-hover:opacity-100"
          style={{ left: `${(player.currentMs / total) * 100}%` }}
        />
      </div>

      <span className="w-14 font-mono text-[11px] tabular-nums text-[var(--text-faint)]">
        {ts(player.durationMs)}
      </span>

      <select
        value={player.rate}
        onChange={(e) => player.setRate(Number(e.target.value))}
        title="Playback speed"
        className="rounded border border-[var(--border)] bg-[var(--bg-inset)] px-1.5 py-1 text-[11px] text-[var(--text-dim)] focus:outline-none"
      >
        {RATES.map((r) => (
          <option key={r} value={r}>
            {r}×
          </option>
        ))}
      </select>
    </div>
  );
}
