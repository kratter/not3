import { useEffect, useMemo, useRef } from "react";

import type { Highlight, Segment, Speaker } from "../api";
import type { Player } from "../hooks";
import { cx, speakerHue, ts } from "../util";

/**
 * The transcript, with the line currently playing kept in view.
 *
 * Every line is clickable and seeks. That single behaviour is what makes the
 * generated material believable: any claim the app makes can be checked
 * against the recording in one click.
 */
export function Transcript({
  segments, speakers, highlights, player, focusSegmentId,
}: {
  segments: Segment[];
  speakers: Speaker[];
  highlights: Highlight[];
  player: Player;
  focusSegmentId: number | null;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLDivElement>(null);
  const userScrolled = useRef(false);

  const highlighted = useMemo(
    () => new Set(highlights.map((h) => h.segment_id)),
    [highlights],
  );
  const names = useMemo(() => {
    const map = new Map<number, string>();
    for (const s of speakers) map.set(s.id, s.display_name || s.label);
    return map;
  }, [speakers]);

  const activeIndex = useMemo(() => {
    const t = player.currentMs;
    // Linear scan is fine: even a three-hour recording is a few thousand
    // segments, and this runs once per animation frame on a list already in
    // memory.
    for (let i = segments.length - 1; i >= 0; i--) {
      if (segments[i]!.start_ms <= t) return i;
    }
    return -1;
  }, [segments, player.currentMs]);

  // Follow playback, but stop fighting the user the moment they scroll.
  useEffect(() => {
    if (!player.playing || userScrolled.current) return;
    activeRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeIndex, player.playing]);

  useEffect(() => {
    userScrolled.current = false;
  }, [player.playing]);

  // Jump to a specific line when something elsewhere in the app points here.
  useEffect(() => {
    if (focusSegmentId == null) return;
    const el = scroller.current?.querySelector(`[data-segment="${focusSegmentId}"]`);
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focusSegmentId]);

  if (segments.length === 0) {
    return (
      <p className="px-6 py-10 text-center text-[13px] text-[var(--text-faint)]">
        No transcript yet.
      </p>
    );
  }

  let lastSpeaker: number | null = -1;

  return (
    <div
      ref={scroller}
      onWheel={() => (userScrolled.current = true)}
      className="h-full overflow-y-auto px-6 py-4"
    >
      {segments.map((segment, i) => {
        const speakerChanged = segment.speaker_id !== lastSpeaker;
        lastSpeaker = segment.speaker_id;
        const name = segment.speaker_id != null ? names.get(segment.speaker_id) : null;
        const hue = speakerHue(name);
        const active = i === activeIndex;

        return (
          <div key={segment.id} data-segment={segment.id}>
            {speakerChanged && name && (
              <p
                className="mb-1 mt-4 text-[11px] font-semibold uppercase tracking-wide"
                style={{ color: `hsl(${hue} 60% 62%)` }}
              >
                {name}
              </p>
            )}
            <div
              ref={active ? activeRef : undefined}
              onClick={() => player.play(segment.start_ms)}
              className={cx(
                "group -mx-2 flex cursor-pointer gap-3 rounded px-2 py-1 transition-colors",
                active ? "bg-[var(--accent-wash)]" : "hover:bg-[var(--bg-inset)]",
              )}
            >
              <span
                className={cx(
                  "mt-0.5 w-12 shrink-0 select-none text-right font-mono text-[11px] tabular-nums",
                  active ? "text-[var(--accent)]" : "text-[var(--text-faint)]",
                )}
              >
                {ts(segment.start_ms)}
              </span>
              <p
                className={cx(
                  "flex-1 text-[14px] leading-relaxed",
                  active ? "text-[var(--text)]" : "text-[var(--text-dim)]",
                  highlighted.has(segment.id) &&
                    "border-l-2 border-[var(--accent)] -ml-px pl-2",
                )}
              >
                {segment.text}
              </p>
            </div>
          </div>
        );
      })}
      <div className="h-24" />
    </div>
  );
}
