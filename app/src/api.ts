/**
 * Typed client for the local engine.
 *
 * The endpoint and token come from the Rust shell over IPC, never from the
 * page, so the token is not sitting in the DOM. Progress arrives over SSE read
 * with fetch + ReadableStream rather than EventSource, which cannot set an
 * Authorization header.
 */

import { invoke } from "@tauri-apps/api/core";

export interface Endpoint {
  base_url: string;
  token: string;
  pid: number;
}

export interface Note {
  id: number;
  title: string;
  source_name: string;
  source_path: string;
  media_path: string | null;
  duration_ms: number;
  language: string | null;
  status: "new" | "processing" | "ready" | "error";
  asr_backend: string | null;
  asr_model: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  segment_count?: number;
  highlight_count?: number;
  finding_count?: number;
}

export interface Segment {
  id: number;
  note_id: number;
  idx: number;
  start_ms: number;
  end_ms: number;
  text: string;
  speaker_id: number | null;
  speaker_label: string | null;
  speaker_name: string | null;
  confidence: number | null;
  words_json: string | null;
}

export interface Highlight {
  id: number;
  note_id: number;
  segment_id: number;
  start_ms: number;
  end_ms: number;
  quote: string;
  kind: "auto" | "manual";
  reason: string | null;
  importance: number | null;
}

export interface Finding {
  id: number;
  note_id: number;
  lens_id: string;
  lens_version: number;
  category: string;
  quote: string;
  segment_id: number;
  start_ms: number;
  end_ms: number;
  confidence: number;
  rationale: string | null;
}

export interface Job {
  id: number;
  note_id: number;
  stage: string;
  state: "pending" | "running" | "done" | "error" | "skipped";
  progress: number;
  message: string | null;
  error: string | null;
}

export interface Speaker {
  id: number;
  note_id: number;
  label: string;
  display_name: string | null;
}

export interface NoteDetail {
  note: Note;
  sections: Record<string, string>;
  jobs: Job[];
  speakers: Speaker[];
}

export interface LensCategory {
  id: string;
  label: string;
  definition: string;
}

export interface Lens {
  id: string;
  name: string;
  version: number;
  description: string;
  disclaimer: string;
  enabled: boolean;
  builtin: boolean;
  path: string;
  categories: LensCategory[];
}

export interface LensRun {
  lens_id: string;
  model: string;
  runs: number;
  proposed: number;
  kept: number;
  dropped: number;
  avg_ms: number;
}

export interface SearchHit {
  id: number;
  note_id: number;
  start_ms: number;
  end_ms: number;
  text: string;
  title: string;
  source_name: string;
  snippet: string;
}

export interface Status {
  backends: { name: string; path: string }[];
  asr_model: string;
  asr_model_present: boolean;
  vad_model_present: boolean;
  ollama: { url: string; available: boolean; models: string[] };
  worker: { busy: boolean; note_id: number | null; queued: number };
  data_dir: string;
  export_dir: string;
}

export interface EngineSettings {
  asr_model: string;
  asr_backend: string;
  language: string;
  diarizer: string;
  ollama_url: string;
  model_distill: string;
  model_highlight: string;
  model_lens: string;
  chunk_tokens: number;
  quote_match_threshold: number;
  export_dir: string;
}

export type ProgressEvent =
  | { type: "queued"; note_id: number; stages: string[] }
  | { type: "stage"; note_id: number; stage: string; state: string; error?: string }
  | { type: "progress"; note_id: number; stage: string; progress: number; message: string }
  | { type: "cancelled"; note_id: number; stage: string }
  | { type: "error"; note_id: number; stage: string; error: string }
  | { type: "done"; note_id: number };

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

export class Api {
  constructor(private endpoint: Endpoint) {}

  get baseUrl() {
    return this.endpoint.base_url;
  }

  /** Audio is served unauthenticated so it can go straight in an <audio src>. */
  audioUrl(noteId: number) {
    return `${this.endpoint.base_url}/api/notes/${noteId}/audio`;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const res = await fetch(`${this.endpoint.base_url}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${this.endpoint.token}`,
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail ?? detail;
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(detail, res.status);
    }
    return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
  }

  private post<T>(path: string, body?: unknown) {
    return this.request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  private patch<T>(path: string, body: unknown) {
    return this.request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
  }

  status = () => this.request<Status>("/api/status");
  settings = () => this.request<EngineSettings>("/api/settings");
  updateSettings = (patch: Partial<EngineSettings>) =>
    this.patch<EngineSettings>("/api/settings", patch);

  notes = () => this.request<Note[]>("/api/notes");
  note = (id: number) => this.request<NoteDetail>(`/api/notes/${id}`);
  segments = (id: number) => this.request<Segment[]>(`/api/notes/${id}/segments`);
  highlights = (id: number) => this.request<Highlight[]>(`/api/notes/${id}/highlights`);
  findings = (id: number) => this.request<Finding[]>(`/api/notes/${id}/findings`);
  jobs = (id: number) => this.request<Job[]>(`/api/notes/${id}/jobs`);

  importFile = (path: string, stages?: string[]) =>
    this.post<{ note_id: number; duplicate: boolean }>("/api/notes/import", {
      path,
      run: true,
      stages,
    });

  run = (id: number, stages?: string[]) =>
    this.post<{ queued: number }>(`/api/notes/${id}/run`, { stages });
  cancel = (id: number) => this.post<{ cancelled: boolean }>(`/api/notes/${id}/cancel`);
  rename = (id: number, title: string) => this.patch<Note>(`/api/notes/${id}`, { title });
  remove = (id: number) => this.request<void>(`/api/notes/${id}`, { method: "DELETE" });
  renameSpeaker = (speakerId: number, name: string) =>
    this.patch<Speaker>(`/api/speakers/${speakerId}`, { display_name: name });

  lenses = () => this.request<Lens[]>("/api/lenses");
  setLensEnabled = (id: string, enabled: boolean) =>
    this.patch<unknown>(`/api/lenses/${id}`, { enabled });
  lensRuns = () => this.request<LensRun[]>("/api/lens-runs");

  search = (q: string) =>
    this.request<SearchHit[]>(`/api/search?q=${encodeURIComponent(q)}`);

  /** Stream progress events until `signal` aborts. */
  async streamEvents(onEvent: (e: ProgressEvent) => void, signal: AbortSignal) {
    const res = await fetch(`${this.endpoint.base_url}/api/events`, {
      headers: { Authorization: `Bearer ${this.endpoint.token}` },
      signal,
    });
    if (!res.body) return;
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE frames are separated by a blank line; a partial frame stays in
      // the buffer until the rest arrives.
      let split: number;
      while ((split = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);
        for (const line of frame.split("\n")) {
          if (line.startsWith("data: ")) {
            try {
              onEvent(JSON.parse(line.slice(6)) as ProgressEvent);
            } catch {
              /* ignore malformed frame */
            }
          }
        }
      }
    }
  }
}

export async function connect(): Promise<Api> {
  const endpoint = await invoke<Endpoint>("engine_endpoint");
  return new Api(endpoint);
}

export const restartEngine = () => invoke<Endpoint>("restart_engine");
