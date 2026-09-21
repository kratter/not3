export function ts(ms: number, withMs = false): string {
  const total = Math.max(0, Math.floor(ms));
  const s = Math.floor(total / 1000);
  const hh = Math.floor(s / 3600);
  const mm = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  const base =
    hh > 0
      ? `${hh}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`
      : `${mm}:${String(ss).padStart(2, "0")}`;
  return withMs ? `${base}.${String(total % 1000).padStart(3, "0")}` : base;
}

export function duration(ms: number): string {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function relativeDate(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diff = Date.now() - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(then).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: days > 365 ? "numeric" : undefined,
  });
}

/** Turn a lens category id into something readable: all_or_nothing -> All or nothing. */
export function humanize(id: string): string {
  const spaced = id.replace(/_/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Stable colour per speaker, so the same person keeps a colour across views. */
const SPEAKER_HUES = [265, 175, 25, 330, 200, 95, 305, 45];
export function speakerHue(key: string | null | undefined): number {
  if (!key) return 0;
  let hash = 0;
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) | 0;
  return SPEAKER_HUES[Math.abs(hash) % SPEAKER_HUES.length]!;
}

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
