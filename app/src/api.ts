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

export interface NoteComment {
  id: number;
  note_id: number;
  author: string;
  content: string;
  timestamp_ms: number | null;
  created_at: string;
  updated_at: string;
}

export interface NoteDetail {
  note: Note;
  sections: Record<string, string>;
  jobs: Job[];
  speakers: Speaker[];
  plus_notes?: string;
  comments?: NoteComment[];
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
  diarize_models_present?: boolean;
  ollama: { url: string; available: boolean; models: string[] };
  worker: { busy: boolean; note_id: number | null; queued: number };
  data_dir: string;
  export_dir: string;
}

export interface SetupEvent {
  stage: string;
  item: string;
  percent: number;
  bytes_done: number;
  bytes_total: number;
  message: string;
  error: string | null;
  is_running: boolean;
}

export interface SetupStatus {
  ready: boolean;
  whisper: {
    installed: boolean;
    backends: string[];
  };
  speech_models: {
    asr_model: string;
    asr_present: boolean;
    vad_model: string;
    vad_present: boolean;
  };
  diarizer: {
    installed: boolean;
    segmentation_present: boolean;
    embedding_present: boolean;
  };
  ollama: {
    installed: boolean;
    running: boolean;
    url: string;
    default_model: string;
    model_present: boolean;
    models: string[];
  };
  progress: SetupEvent;
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

export interface NoteExport {
  note_id: number;
  title: string;
  filename: string;
  path: string;
  exists: boolean;
  content: string;
}

export interface ActionItem {
  id: number;
  note_id: number;
  note_title: string;
  assignee: string;
  text: string;
  raw: string;
  completed: boolean;
  created_at: string;
}

export interface PatternMatrix {
  total_notes: number;
  total_findings: number;
  by_lens: Array<{ lens_id: string; count: number }>;
  by_category: Array<{ lens_id: string; category: string; count: number }>;
  by_speaker: Array<{ speaker_name: string; count: number }>;
  matrix: Array<{ lens_id: string; category: string; speaker_name: string; count: number }>;
}

export interface InsightSearchHit {
  id: number;
  note_id: number;
  lens_id: string;
  category: string;
  quote: string;
  confidence: number;
  rationale: string | null;
  start_ms: number;
  end_ms: number;
  created_at: string;
  title: string;
  source_name: string;
  speaker_name: string;
}

export interface Citation {
  index: number;
  note_id: number;
  note_title: string;
  start_ms: number;
  end_ms: number;
  speaker: string;
  quote: string;
  type: "transcript" | "finding" | "section";
}

export interface AskResponse {
  query: string;
  answer: string;
  citations: Citation[];
  evidence_count: number;
}

export interface SystemMetrics {
  timestamp: number;
  cpu: {
    percent: number;
    cores: number;
  };
  memory: {
    percent: number;
    used_gb: number;
    total_gb: number;
  };
  gpu: {
    available: boolean;
    name: string;
    utilization: number;
    memory_used_mb: number;
    memory_total_mb: number;
    memory_percent: number;
    temperature: number;
  };
  ai: {
    busy: boolean;
    stage: string | null;
    note_id: number | null;
    asr_backend: string | null;
    asr_model: string | null;
    llm_model: string | null;
    load_percent: number;
  };
}



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

  private put<T>(path: string, body: unknown) {
    return this.request<T>(path, { method: "PUT", body: JSON.stringify(body) });
  }

  private delete<T>(path: string) {
    return this.request<T>(path, { method: "DELETE" });
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

  importFile = (
    path: string,
    options?: { stages?: string[]; lenses?: string[]; style?: string },
  ) =>
    this.post<{ note_id: number; duplicate: boolean }>("/api/notes/import", {
      path,
      run: true,
      stages: options?.stages,
      lenses: options?.lenses,
      style: options?.style ?? "executive",
    });

  createTextNote = (req: {
    title?: string;
    text: string;
    formalize?: boolean;
    style?: string;
    run?: boolean;
    stages?: string[];
    lenses?: string[];
  }) =>
    this.post<{ note_id: number; duplicate: boolean }>("/api/notes/text", {
      run: true,
      formalize: true,
      style: "formal",
      ...req,
    });

  run = (
    id: number,
    options?: { stages?: string[]; lenses?: string[]; style?: string } | string[],
  ) => {
    const opts = Array.isArray(options)
      ? { stages: options }
      : options;
    return this.post<{ queued: number }>(`/api/notes/${id}/run`, {
      stages: opts?.stages,
      lenses: opts?.lenses,
      style: opts?.style ?? "executive",
    });
  };

  getExport = (id: number) => this.request<NoteExport>(`/api/notes/${id}/export`);
  writeExport = (id: number) => this.post<NoteExport>(`/api/notes/${id}/export`);

  cancel = (id: number) => this.post<{ cancelled: boolean }>(`/api/notes/${id}/cancel`);
  resetNote = (id: number) => this.post<{ reset: boolean }>(`/api/notes/${id}/reset`);
  rename = (id: number, title: string) => this.patch<Note>(`/api/notes/${id}`, { title });
  remove = (id: number) => this.request<void>(`/api/notes/${id}`, { method: "DELETE" });
  renameSpeaker = (speakerId: number, name: string) =>
    this.patch<Speaker>(`/api/speakers/${speakerId}`, { display_name: name });

  // App Security & Password Protection
  authStatus = () => this.request<{ password_required: boolean }>("/api/auth/status");
  authVerify = (password: string) => this.post<{ ok: boolean }>("/api/auth/verify", { password });
  setAuthPassword = (password: string, currentPassword?: string) =>
    this.post<{ ok: boolean }>("/api/auth/set_password", {
      password,
      current_password: currentPassword,
    });
  removeAuthPassword = (currentPassword: string) =>
    this.post<{ ok: boolean }>("/api/auth/remove_password", {
      current_password: currentPassword,
    });

  // Note AI Chat & Reformatting
  noteChat = (
    noteId: number,
    prompt: string,
    history: Array<{ role: string; content: string }> = [],
    model?: string
  ) =>
    this.post<{ reply: string; model: string }>(`/api/notes/${noteId}/chat`, {
      prompt,
      history,
      model,
    });

  // Note Sections Update
  updateNoteSection = (
    noteId: number,
    kind: string,
    content_md: string,
    model?: string
  ) =>
    this.put<{ ok: boolean; kind: string; content_md: string }>(
      `/api/notes/${noteId}/sections/${kind}`,
      { content_md, model }
    );

  // Plus Notes
  getPlusNotes = (noteId: number) =>
    this.request<{ plus_notes: string }>(`/api/notes/${noteId}/plus_notes`);
  savePlusNotes = (noteId: number, content: string) =>
    this.put<{ ok: boolean; plus_notes: string }>(`/api/notes/${noteId}/plus_notes`, {
      content,
    });

  // Note Comments
  getComments = (noteId: number) =>
    this.request<NoteComment[]>(`/api/notes/${noteId}/comments`);
  addComment = (
    noteId: number,
    data: { content: string; author?: string; timestamp_ms?: number | null }
  ) => this.post<NoteComment>(`/api/notes/${noteId}/comments`, data);
  deleteComment = (noteId: number, commentId: number) =>
    this.delete<{ ok: boolean; deleted: number }>(`/api/notes/${noteId}/comments/${commentId}`);


  lenses = () => this.request<Lens[]>("/api/lenses");
  setLensEnabled = (id: string, enabled: boolean) =>
    this.patch<unknown>(`/api/lenses/${id}`, { enabled });
  lensRuns = () => this.request<LensRun[]>("/api/lens-runs");

  search = (q: string) =>
    this.request<SearchHit[]>(`/api/search?q=${encodeURIComponent(q)}`);

  uploadLens = (yaml: string) => this.post<Lens>("/api/lenses", { yaml });
  removeLens = (id: string) =>
    this.request<{ deleted: string }>(`/api/lenses/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
  getLensYaml = (id: string) =>
    this.request<{ id: string; name: string; path: string; yaml: string }>(
      `/api/lenses/${encodeURIComponent(id)}/yaml`
    );
  getSampleLensTemplate = () =>
    this.request<{ filename: string; yaml: string }>("/api/lenses/sample-template");

  seedSampleLibrary = () => this.post<{ seeded: boolean; notes: Note[] }>("/api/library/sample");
  exportLibrary = () => this.request<Record<string, unknown>>("/api/library/export");
  importLibrary = (pkg: Record<string, unknown>) =>
    this.post<{ imported_notes: number; imported_segments: number; imported_findings: number }>(
      "/api/library/import",
      pkg
    );

  getActions = () => this.request<ActionItem[]>("/api/insights/actions");
  getPatterns = () => this.request<PatternMatrix>("/api/insights/patterns");
  searchInsights = (params: {
    q?: string;
    lens_id?: string;
    category?: string;
    speaker_id?: number;
    limit?: number;
  }) => {
    const qp = new URLSearchParams();
    if (params.q) qp.set("q", params.q);
    if (params.lens_id) qp.set("lens_id", params.lens_id);
    if (params.category) qp.set("category", params.category);
    if (params.speaker_id != null) qp.set("speaker_id", String(params.speaker_id));
    if (params.limit != null) qp.set("limit", String(params.limit));
    return this.request<InsightSearchHit[]>(`/api/insights/search?${qp.toString()}`);
  };
  askLibrary = (query: string, noteIds?: number[]) =>
    this.post<AskResponse>("/api/insights/ask", { query, note_ids: noteIds });

  systemMetrics = () => this.request<SystemMetrics>("/api/system/metrics");

  setupStatus = () => this.request<SetupStatus>("/api/setup/status");

  startSetup = (req?: { install_ollama?: boolean; pull_llm?: boolean }) =>
    this.post<{ started: boolean }>("/api/setup/start", req ?? {});

  async streamSetupEvents(onEvent: (e: SetupEvent) => void, signal: AbortSignal) {
    const res = await fetch(`${this.endpoint.base_url}/api/setup/events`, {
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
      let split: number;
      while ((split = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);
        for (const line of frame.split("\n")) {
          if (line.startsWith("data: ")) {
            try {
              onEvent(JSON.parse(line.slice(6)) as SetupEvent);
            } catch {
              /* ignore malformed frame */
            }
          }
        }
      }
    }
  }

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
