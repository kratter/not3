import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";

import {
  Api,
  connect,
  type Finding,
  type Highlight,
  type Job,
  type NoteDetail,
  type ProgressEvent,
  type Segment,
} from "./api";

type EngineStatus =
  | { state: "connecting" }
  | { state: "ready"; api: Api }
  | { state: "failed"; error: string };

/** Connect to the engine and stay connected across restarts. */
export function useEngine() {
  const [status, setStatus] = useState<EngineStatus>({ state: "connecting" });

  const attempt = useCallback(async () => {
    try {
      setStatus({ state: "ready", api: await connect() });
    } catch (err) {
      setStatus({ state: "failed", error: String(err) });
    }
  }, []);

  useEffect(() => {
    void attempt();
    // The shell starts the engine on a background thread, so the first
    // attempt can lose the race; these events are the authoritative signal.
    const ready = listen("engine://ready", () => void attempt());
    const failed = listen<string>("engine://failed", (e) =>
      setStatus({ state: "failed", error: e.payload }),
    );
    const exited = listen<number>("engine://exited", (e) =>
      setStatus({
        state: "failed",
        error: `The engine stopped unexpectedly (exit code ${e.payload}).`,
      }),
    );
    return () => {
      void ready.then((un) => un());
      void failed.then((un) => un());
      void exited.then((un) => un());
    };
  }, [attempt]);

  return { status, retry: attempt };
}

/** Subscribe to pipeline progress. */
export function useProgress(api: Api | null) {
  const [events, setEvents] = useState<Map<number, Map<string, ProgressEvent>>>(
    () => new Map(),
  );
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!api) return;
    const controller = new AbortController();
    void api
      .streamEvents((event) => {
        setEvents((prev) => {
          const next = new Map(prev);
          const forNote = new Map(next.get(event.note_id) ?? []);
          const stage = "stage" in event ? event.stage : "_";
          forNote.set(stage, event);
          next.set(event.note_id, forNote);
          return next;
        });
        // Terminal events change data the views already fetched, so they need
        // to refetch; progress events only move a bar.
        if (event.type === "done" || event.type === "error" || event.type === "stage") {
          setTick((t) => t + 1);
        }
      }, controller.signal)
      .catch(() => {
        /* aborted or engine gone; useEngine reports it */
      });
    return () => controller.abort();
  }, [api]);

  const activeFor = useCallback(
    (noteId: number) => {
      const forNote = events.get(noteId);
      if (!forNote) return null;
      for (const event of forNote.values()) {
        if (event.type === "progress") return event;
        if (event.type === "stage" && event.state === "running") return event;
      }
      return null;
    },
    [events],
  );

  return { events, activeFor, tick };
}

export interface NoteData {
  detail: NoteDetail | null;
  segments: Segment[];
  highlights: Highlight[];
  findings: Finding[];
  jobs: Job[];
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useNoteData(api: Api | null, noteId: number | null, tick: number): NoteData {
  const [data, setData] = useState<Omit<NoteData, "reload">>({
    detail: null,
    segments: [],
    highlights: [],
    findings: [],
    jobs: [],
    loading: false,
    error: null,
  });
  const [manual, setManual] = useState(0);

  useEffect(() => {
    if (!api || noteId == null) {
      setData({
        detail: null, segments: [], highlights: [], findings: [], jobs: [],
        loading: false, error: null,
      });
      return;
    }
    let cancelled = false;
    setData((d) => ({ ...d, loading: true, error: null }));
    void Promise.all([
      api.note(noteId),
      api.segments(noteId),
      api.highlights(noteId),
      api.findings(noteId),
    ])
      .then(([detail, segments, highlights, findings]) => {
        if (cancelled) return;
        setData({
          detail, segments, highlights, findings,
          jobs: detail.jobs, loading: false, error: null,
        });
      })
      .catch((err) => {
        if (!cancelled) {
          setData((d) => ({ ...d, loading: false, error: String(err?.message ?? err) }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, noteId, tick, manual]);

  return { ...data, reload: () => setManual((m) => m + 1) };
}

export interface Player {
  ref: React.RefObject<HTMLAudioElement | null>;
  src: string | null;
  playing: boolean;
  currentMs: number;
  durationMs: number;
  toggle: () => void;
  seek: (ms: number) => void;
  play: (ms?: number) => void;
  skip: (deltaMs: number) => void;
  rate: number;
  setRate: (rate: number) => void;
}

/** Audio playback. Every quote in the app routes through `play`. */
export function usePlayer(src: string | null, fallbackDurationMs = 0): Player {
  const ref = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [currentMs, setCurrentMs] = useState(0);
  const [durationMs, setDurationMs] = useState(fallbackDurationMs);
  const [rate, setRateState] = useState(1);

  useEffect(() => {
    setPlaying(false);
    setCurrentMs(0);
    setDurationMs(fallbackDurationMs);
  }, [src, fallbackDurationMs]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // requestAnimationFrame rather than timeupdate: timeupdate fires about
    // 4x a second, which makes the transcript's active line visibly lag.
    let frame = 0;
    const loop = () => {
      setCurrentMs(el.currentTime * 1000);
      frame = requestAnimationFrame(loop);
    };
    const onPlay = () => {
      setPlaying(true);
      frame = requestAnimationFrame(loop);
    };
    const onPause = () => {
      setPlaying(false);
      cancelAnimationFrame(frame);
      setCurrentMs(el.currentTime * 1000);
    };
    const onMeta = () => {
      if (Number.isFinite(el.duration)) setDurationMs(el.duration * 1000);
    };
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onPause);
    el.addEventListener("loadedmetadata", onMeta);
    return () => {
      cancelAnimationFrame(frame);
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onPause);
      el.removeEventListener("loadedmetadata", onMeta);
    };
  }, [src]);

  const seek = useCallback((ms: number) => {
    const el = ref.current;
    if (!el) return;
    el.currentTime = Math.max(0, ms / 1000);
    setCurrentMs(Math.max(0, ms));
  }, []);

  const play = useCallback(
    (ms?: number) => {
      const el = ref.current;
      if (!el) return;
      if (ms != null) el.currentTime = Math.max(0, ms / 1000);
      void el.play().catch(() => undefined);
    },
    [],
  );

  const toggle = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    if (el.paused) void el.play().catch(() => undefined);
    else el.pause();
  }, []);

  const skip = useCallback(
    (delta: number) => seek((ref.current?.currentTime ?? 0) * 1000 + delta),
    [seek],
  );

  const setRate = useCallback((value: number) => {
    setRateState(value);
    if (ref.current) ref.current.playbackRate = value;
  }, []);

  return useMemo(
    () => ({ ref, src, playing, currentMs, durationMs, toggle, seek, play, skip, rate, setRate }),
    [src, playing, currentMs, durationMs, toggle, seek, play, skip, rate, setRate],
  );
}

/** Theme, remembered across launches. */
export function useTheme() {
  const [theme, setTheme] = useState<"dark" | "light">(
    () => (localStorage.getItem("not3.theme") as "dark" | "light") ?? "dark",
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("not3.theme", theme);
  }, [theme]);
  return { theme, toggle: () => setTheme((t) => (t === "dark" ? "light" : "dark")) };
}
