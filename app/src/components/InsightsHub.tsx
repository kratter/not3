import { useEffect, useState } from "react";
import type { ActionItem, Api, AskResponse, InsightSearchHit, Lens, Note, PatternMatrix } from "../api";
import { cx, ts } from "../util";
import { Button, Chip, Empty, Icon, Modal, Spinner } from "./ui";

interface InsightsHubProps {
  api: Api;
  notes: Note[];
  lenses: Lens[];
  onSelectNote: (noteId: number, seekMs?: number) => void;
  onRefreshLibrary: () => void;
  onClose: () => void;
}

type TabKey = "ask" | "actions" | "patterns" | "lab";

export function InsightsHub({
  api,
  notes,
  lenses,
  onSelectNote,
  onRefreshLibrary,
  onClose,
}: InsightsHubProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("ask");

  // Ask state
  const [askQuery, setAskQuery] = useState("");
  const [asking, setAsking] = useState(false);
  const [askResult, setAskResult] = useState<AskResponse | null>(null);
  const [askError, setAskError] = useState<string | null>(null);

  // Actions state
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [loadingActions, setLoadingActions] = useState(false);
  const [actionFilter, setActionFilter] = useState("");
  const [completedMap, setCompletedMap] = useState<Record<number, boolean>>({});

  // Patterns state
  const [patterns, setPatterns] = useState<PatternMatrix | null>(null);
  const [loadingPatterns, setLoadingPatterns] = useState(false);
  const [selectedLensFilter, setSelectedLensFilter] = useState<string>("");
  const [findingHits, setFindingHits] = useState<InsightSearchHit[]>([]);

  // Lens Lab & Library state
  const [seeding, setSeeding] = useState(false);
  const [seedMessage, setSeedMessage] = useState<string | null>(null);
  const [editingYaml, setEditingYaml] = useState<string | null>(null);
  const [yamlLensName, setYamlLensName] = useState("");
  const [yamlError, setYamlError] = useState<string | null>(null);
  const [savingLens, setSavingLens] = useState(false);
  const [importingLib, setImportingLib] = useState(false);
  const [libMessage, setLibMessage] = useState<string | null>(null);

  // Load actions & patterns when switching tabs
  useEffect(() => {
    if (activeTab === "actions" && actions.length === 0) {
      setLoadingActions(true);
      api
        .getActions()
        .then(setActions)
        .catch(() => undefined)
        .finally(() => setLoadingActions(false));
    } else if (activeTab === "patterns" && !patterns) {
      setLoadingPatterns(true);
      api
        .getPatterns()
        .then(setPatterns)
        .catch(() => undefined)
        .finally(() => setLoadingPatterns(false));
    }
  }, [activeTab, actions.length, patterns, api]);

  // Load findings when lens filter changes in patterns tab
  useEffect(() => {
    if (activeTab === "patterns") {
      api
        .searchInsights({ lens_id: selectedLensFilter || undefined, limit: 30 })
        .then(setFindingHits)
        .catch(() => setFindingHits([]));
    }
  }, [activeTab, selectedLensFilter, api]);

  async function handleAsk(queryToRun?: string) {
    const q = queryToRun || askQuery;
    if (!q.trim()) return;
    setAsking(true);
    setAskError(null);
    try {
      const res = await api.askLibrary(q);
      setAskResult(res);
    } catch (err) {
      setAskError(err instanceof Error ? err.message : String(err));
    } finally {
      setAsking(false);
    }
  }

  async function handleSeedSample() {
    setSeeding(true);
    setSeedMessage(null);
    try {
      const res = await api.seedSampleLibrary();
      setSeedMessage(`Seeded ${res.notes.length} reference sessions with multi-speaker transcripts, action items, and pattern findings!`);
      onRefreshLibrary();
      // Reload actions and patterns
      void api.getActions().then(setActions);
      void api.getPatterns().then(setPatterns);
    } catch (err) {
      setSeedMessage(`Error seeding: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSeeding(false);
    }
  }

  async function handleDownloadSampleLens() {
    try {
      const { filename, yaml } = await api.getSampleLensTemplate();
      const blob = new Blob([yaml], { type: "text/yaml;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(`Could not download template: ${String(err)}`);
    }
  }

  async function handleExportLibrary() {
    try {
      const data = await api.exportLibrary();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `not3_library_${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setLibMessage("Library exported successfully!");
    } catch (err) {
      setLibMessage(`Export failed: ${String(err)}`);
    }
  }

  async function handleImportFile(file: File) {
    setImportingLib(true);
    setLibMessage(null);
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as Record<string, unknown>;
      const res = await api.importLibrary(parsed);
      setLibMessage(`Imported ${res.imported_notes} notes, ${res.imported_segments} segments, ${res.imported_findings} findings!`);
      onRefreshLibrary();
      void api.getActions().then(setActions);
      void api.getPatterns().then(setPatterns);
    } catch (err) {
      setLibMessage(`Import failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setImportingLib(false);
    }
  }

  async function handleUploadLensFile(file: File) {
    setSavingLens(true);
    setYamlError(null);
    try {
      const content = await file.text();
      await api.uploadLens(content);
      onRefreshLibrary();
      setSeedMessage(`Lens uploaded and registered successfully!`);
    } catch (err) {
      alert(`Failed to upload lens: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSavingLens(false);
    }
  }

  async function handleSaveCustomLens() {
    if (!editingYaml) return;
    setSavingLens(true);
    setYamlError(null);
    try {
      await api.uploadLens(editingYaml);
      onRefreshLibrary();
      setEditingYaml(null);
    } catch (err) {
      setYamlError(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingLens(false);
    }
  }

  async function handleDeleteLens(id: string) {
    if (!confirm(`Delete custom lens "${id}"? This cannot be undone.`)) return;
    try {
      await api.removeLens(id);
      onRefreshLibrary();
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleViewLensYaml(id: string) {
    try {
      const data = await api.getLensYaml(id);
      setYamlLensName(data.name);
      setEditingYaml(data.yaml);
      setYamlError(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    }
  }

  // Filtered actions
  const filteredActions = actions.filter((a) => {
    if (!actionFilter) return true;
    const term = actionFilter.toLowerCase();
    return (
      a.text.toLowerCase().includes(term) ||
      a.assignee.toLowerCase().includes(term) ||
      a.note_title.toLowerCase().includes(term)
    );
  });

  return (
    <div className="flex h-full flex-col bg-[var(--bg)] text-[var(--text)]">
      {/* Header */}
      <header className="flex shrink-0 items-center justify-between border-b border-[var(--border)] bg-[var(--bg-raised)] px-6 py-3.5">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--accent)]/10 text-[var(--accent)]">
            <Icon name="sparkles" className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-[15px] font-semibold tracking-tight">Library Intelligence & Insights</h1>
            <p className="text-[12px] text-[var(--text-faint)]">
              Cross-note synthesis, global commitments, pattern diagnostics, and lens authoring
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Tabs */}
          <nav className="flex rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] p-0.5 text-[12px]">
            <button
              type="button"
              onClick={() => setActiveTab("ask")}
              className={cx(
                "flex items-center gap-1.5 rounded-md px-3 py-1 font-medium transition-colors",
                activeTab === "ask"
                  ? "bg-[var(--bg-raised)] text-[var(--text)] shadow-xs"
                  : "text-[var(--text-faint)] hover:text-[var(--text)]",
              )}
            >
              <Icon name="search" className="h-3 w-3" />
              Ask Library
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("actions")}
              className={cx(
                "flex items-center gap-1.5 rounded-md px-3 py-1 font-medium transition-colors",
                activeTab === "actions"
                  ? "bg-[var(--bg-raised)] text-[var(--text)] shadow-xs"
                  : "text-[var(--text-faint)] hover:text-[var(--text)]",
              )}
            >
              <Icon name="check" className="h-3 w-3" />
              Action Matrix
              {actions.length > 0 && (
                <span className="ml-0.5 rounded-full bg-[var(--accent)]/20 px-1.5 py-0.2 text-[10px] text-[var(--accent)] font-semibold">
                  {actions.length}
                </span>
              )}
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("patterns")}
              className={cx(
                "flex items-center gap-1.5 rounded-md px-3 py-1 font-medium transition-colors",
                activeTab === "patterns"
                  ? "bg-[var(--bg-raised)] text-[var(--text)] shadow-xs"
                  : "text-[var(--text-faint)] hover:text-[var(--text)]",
              )}
            >
              <Icon name="sparkles" className="h-3 w-3" />
              Pattern Analytics
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("lab")}
              className={cx(
                "flex items-center gap-1.5 rounded-md px-3 py-1 font-medium transition-colors",
                activeTab === "lab"
                  ? "bg-[var(--bg-raised)] text-[var(--text)] shadow-xs"
                  : "text-[var(--text-faint)] hover:text-[var(--text)]",
              )}
            >
              <Icon name="settings" className="h-3 w-3" />
              Lens Lab & Ops
            </button>
          </nav>

          <Button variant="outline" size="sm" onClick={onClose} title="Close Insights Hub">
            <Icon name="x" className="h-3.5 w-3.5" />
            Close
          </Button>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="min-h-0 flex-1 overflow-y-auto p-6">
        {/* TAB 1: ASK YOUR LIBRARY */}
        {activeTab === "ask" && (
          <div className="mx-auto max-w-3xl space-y-6">
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-raised)] p-6 shadow-xs">
              <label className="block text-[13px] font-medium text-[var(--text-dim)] mb-2">
                Ask anything across your entire recording and note collection:
              </label>

              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Icon
                    name="search"
                    className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-faint)]"
                  />
                  <input
                    value={askQuery}
                    onChange={(e) => setAskQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && void handleAsk()}
                    placeholder="e.g. What were the key architecture and security decisions made?"
                    className="w-full rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] py-2.5 pl-9 pr-3 text-[14px] text-[var(--text)] placeholder:text-[var(--text-faint)] focus:border-[var(--accent)] focus:outline-none"
                  />
                </div>
                <Button
                  variant="solid"
                  onClick={() => void handleAsk()}
                  disabled={asking || !askQuery.trim()}
                  className="px-5 font-semibold"
                >
                  {asking ? <Spinner className="h-4 w-4" /> : <Icon name="sparkles" className="h-4 w-4" />}
                  {asking ? "Synthesizing…" : "Ask Library"}
                </Button>
              </div>

              {/* Sample Prompt Pills */}
              <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px] text-[var(--text-faint)]">
                <span>Try asking:</span>
                {[
                  "What architecture decisions were made?",
                  "What did Dr. Vance commit to delivering?",
                  "Summarize the clinician charting burnout pain points",
                  "What did Liam discuss regarding ONNX batching?",
                ].map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => {
                      setAskQuery(prompt);
                      void handleAsk(prompt);
                    }}
                    className="rounded-md border border-[var(--border)] bg-[var(--bg)] px-2 py-0.5 hover:border-[var(--accent)] hover:text-[var(--text)] transition-colors"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>

            {askError && (
              <div className="rounded-lg border border-[var(--bad)]/30 bg-[var(--bad)]/10 p-3 text-[12px] text-[var(--bad)]">
                {askError}
              </div>
            )}

            {/* Answer Display */}
            {askResult && (
              <div className="space-y-4 rounded-xl border border-[var(--border)] bg-[var(--bg-raised)] p-6 shadow-xs animate-in fade-in duration-200">
                <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
                  <div className="flex items-center gap-2">
                    <Icon name="sparkles" className="h-4 w-4 text-[var(--accent)]" />
                    <span className="text-[13px] font-semibold">Synthesized Answer</span>
                  </div>
                  <Chip tone="accent">
                    {askResult.citations.length} cited evidence {askResult.citations.length === 1 ? "point" : "points"}
                  </Chip>
                </div>

                <div className="whitespace-pre-wrap text-[14px] leading-relaxed text-[var(--text)]">
                  {askResult.answer}
                </div>

                {/* Citations List */}
                {askResult.citations.length > 0 && (
                  <div className="mt-6 border-t border-[var(--border)] pt-4">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-faint)] mb-2">
                      Cited Sources & Verbatim Excerpts
                    </p>
                    <div className="space-y-2">
                      {askResult.citations.map((c) => (
                        <div
                          key={c.index}
                          className="flex items-start justify-between gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] p-3 hover:border-[var(--accent)]/50 transition-colors"
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 text-[12px] font-medium text-[var(--text)]">
                              <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-[var(--accent)] text-[10px] text-white font-bold">
                                {c.index}
                              </span>
                              <span className="truncate">{c.note_title}</span>
                              <span className="text-[var(--text-faint)]">·</span>
                              <span className="text-[var(--text-faint)]">{ts(c.start_ms)}</span>
                              <span className="text-[var(--text-faint)]">·</span>
                              <span className="text-[var(--accent)]">{c.speaker}</span>
                            </div>
                            <p className="mt-1 text-[12px] italic text-[var(--text-dim)]">
                              “{c.quote}”
                            </p>
                          </div>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onSelectNote(c.note_id, c.start_ms)}
                            className="shrink-0 text-xs"
                            title="Jump to note and listen at this timestamp"
                          >
                            <Icon name="play" className="h-3 w-3" />
                            Jump to audio
                          </Button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* TAB 2: GLOBAL ACTION MATRIX */}
        {activeTab === "actions" && (
          <div className="mx-auto max-w-4xl space-y-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-[16px] font-semibold">Global Action Items & Commitments</h2>
                <p className="text-[12px] text-[var(--text-faint)]">
                  All extracted commitments and action points aggregated across your library
                </p>
              </div>
              <div className="w-64">
                <input
                  value={actionFilter}
                  onChange={(e) => setActionFilter(e.target.value)}
                  placeholder="Filter by assignee or keyword…"
                  className="w-full rounded-md border border-[var(--border)] bg-[var(--bg-inset)] px-3 py-1.5 text-[12px] focus:border-[var(--accent)] focus:outline-none"
                />
              </div>
            </div>

            {loadingActions ? (
              <div className="flex justify-center py-12">
                <Spinner className="h-6 w-6" />
              </div>
            ) : filteredActions.length === 0 ? (
              <Empty
                title="No Action Items Found"
                hint={
                  notes.length === 0
                    ? "Add a recording or seed the reference sample library to see commitments."
                    : "No action items extracted matching this filter."
                }
              />
            ) : (
              <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg-raised)] shadow-xs">
                <table className="w-full text-left text-[13px]">
                  <thead className="border-b border-[var(--border)] bg-[var(--bg-inset)] text-[11px] uppercase tracking-wider text-[var(--text-faint)]">
                    <tr>
                      <th className="px-4 py-2.5 w-10 text-center">Status</th>
                      <th className="px-4 py-2.5 w-44">Assignee / Owner</th>
                      <th className="px-4 py-2.5">Action Commitment</th>
                      <th className="px-4 py-2.5 w-52">Source Note</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {filteredActions.map((item) => {
                      const isDone = completedMap[item.id] ?? item.completed;
                      return (
                        <tr
                          key={item.id}
                          className={cx(
                            "transition-colors hover:bg-[var(--bg-inset)]/50",
                            isDone && "opacity-60",
                          )}
                        >
                          <td className="px-4 py-3 text-center">
                            <input
                              type="checkbox"
                              checked={isDone}
                              onChange={(e) =>
                                setCompletedMap((prev) => ({
                                  ...prev,
                                  [item.id]: e.target.checked,
                                }))
                              }
                              className="h-4 w-4 rounded border-[var(--border)] text-[var(--accent)] focus:ring-0 cursor-pointer"
                            />
                          </td>
                          <td className="px-4 py-3 font-medium">
                            {item.assignee ? (
                              <Chip tone="accent">{item.assignee}</Chip>
                            ) : (
                              <span className="text-[var(--text-faint)]">Unassigned</span>
                            )}
                          </td>
                          <td className={cx("px-4 py-3 leading-relaxed", isDone && "line-through text-[var(--text-faint)]")}>
                            {item.text}
                          </td>
                          <td className="px-4 py-3">
                            <button
                              type="button"
                              onClick={() => onSelectNote(item.note_id)}
                              className="truncate text-left text-[12px] font-medium text-[var(--accent)] hover:underline block max-w-48"
                              title={`Open ${item.note_title}`}
                            >
                              {item.note_title}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: PATTERN ANALYTICS */}
        {activeTab === "patterns" && (
          <div className="mx-auto max-w-4xl space-y-6">
            <div>
              <h2 className="text-[16px] font-semibold">Diagnostic Pattern Analytics & Frequency Matrix</h2>
              <p className="text-[12px] text-[var(--text-faint)]">
                Cross-note distribution of behavioral, cognitive, and communication patterns
              </p>
            </div>

            {loadingPatterns || !patterns ? (
              <div className="flex justify-center py-12">
                <Spinner className="h-6 w-6" />
              </div>
            ) : (
              <>
                {/* Metric Summary Cards */}
                <div className="grid grid-cols-3 gap-4">
                  <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-raised)] p-4 shadow-xs">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">Total Findings</p>
                    <p className="mt-1 text-2xl font-bold text-[var(--text)]">{patterns.total_findings}</p>
                    <p className="text-[11px] text-[var(--text-faint)]">Anchored with verbatim quotes</p>
                  </div>
                  <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-raised)] p-4 shadow-xs">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">Library Notes</p>
                    <p className="mt-1 text-2xl font-bold text-[var(--text)]">{patterns.total_notes}</p>
                    <p className="text-[11px] text-[var(--text-faint)]">Indexed with FTS5 search</p>
                  </div>
                  <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-raised)] p-4 shadow-xs">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">Active Lenses</p>
                    <p className="mt-1 text-2xl font-bold text-[var(--text)]">{patterns.by_lens.length}</p>
                    <p className="text-[11px] text-[var(--text-faint)]">Shipped & custom lenses</p>
                  </div>
                </div>

                {/* Two Column Breakdown */}
                <div className="grid grid-cols-2 gap-6">
                  {/* By Lens */}
                  <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-raised)] p-5 shadow-xs">
                    <h3 className="text-[13px] font-semibold mb-3">Findings by Lens</h3>
                    <div className="space-y-3">
                      {patterns.by_lens.map((item) => {
                        const pct = patterns.total_findings > 0 ? (item.count / patterns.total_findings) * 100 : 0;
                        return (
                          <div key={item.lens_id}>
                            <div className="flex justify-between text-[12px] mb-1">
                              <span className="font-medium capitalize">{item.lens_id.replace(/_/g, " ")}</span>
                              <span className="text-[var(--text-faint)]">{item.count} ({Math.round(pct)}%)</span>
                            </div>
                            <div className="h-2 w-full rounded-full bg-[var(--bg-inset)] overflow-hidden">
                              <div className="h-full rounded-full bg-[var(--accent)]" style={{ width: `${pct}%` }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* By Speaker */}
                  <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-raised)] p-5 shadow-xs">
                    <h3 className="text-[13px] font-semibold mb-3">Findings by Speaker</h3>
                    <div className="space-y-3">
                      {patterns.by_speaker.map((item) => {
                        const pct = patterns.total_findings > 0 ? (item.count / patterns.total_findings) * 100 : 0;
                        return (
                          <div key={item.speaker_name}>
                            <div className="flex justify-between text-[12px] mb-1">
                              <span className="font-medium">{item.speaker_name}</span>
                              <span className="text-[var(--text-faint)]">{item.count} ({Math.round(pct)}%)</span>
                            </div>
                            <div className="h-2 w-full rounded-full bg-[var(--bg-inset)] overflow-hidden">
                              <div className="h-full rounded-full bg-emerald-500/80" style={{ width: `${pct}%` }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Filterable Findings Feed */}
                <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-raised)] p-5 shadow-xs space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-[13px] font-semibold">Evidence Findings Stream</h3>
                    <select
                      value={selectedLensFilter}
                      onChange={(e) => setSelectedLensFilter(e.target.value)}
                      className="rounded-md border border-[var(--border)] bg-[var(--bg-inset)] px-2.5 py-1 text-[12px] focus:border-[var(--accent)] focus:outline-none"
                    >
                      <option value="">All Lenses</option>
                      {lenses.map((l) => (
                        <option key={l.id} value={l.id}>{l.name}</option>
                      ))}
                    </select>
                  </div>

                  <div className="space-y-2">
                    {findingHits.map((h) => (
                      <div
                        key={h.id}
                        onClick={() => onSelectNote(h.note_id, h.start_ms)}
                        className="group flex items-start justify-between gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] p-3 hover:border-[var(--accent)]/60 cursor-pointer transition-colors"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 text-[11px] text-[var(--text-faint)]">
                            <Chip tone="accent">{h.category.replace(/_/g, " ")}</Chip>
                            <span>{h.title || h.source_name}</span>
                            <span>·</span>
                            <span>{ts(h.start_ms)}</span>
                            {h.speaker_name && (
                              <>
                                <span>·</span>
                                <span className="font-medium text-[var(--text)]">{h.speaker_name}</span>
                              </>
                            )}
                          </div>
                          <p className="mt-1 text-[13px] text-[var(--text)] leading-snug">
                            “{h.quote}”
                          </p>
                          {h.rationale && (
                            <p className="mt-0.5 text-[11px] text-[var(--text-dim)]">
                              Rationale: {h.rationale}
                            </p>
                          )}
                        </div>
                        <Icon name="play" className="h-4 w-4 text-[var(--text-faint)] group-hover:text-[var(--accent)] shrink-0 transition-colors" />
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* TAB 4: LENS LAB & OPERATIONS */}
        {activeTab === "lab" && (
          <div className="mx-auto max-w-4xl space-y-6">
            {/* Seed Sample Library Card */}
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-raised)] p-6 shadow-xs flex items-center justify-between">
              <div>
                <h3 className="text-[14px] font-semibold">Reference Sample Library</h3>
                <p className="mt-1 text-[12px] text-[var(--text-faint)] max-w-xl">
                  Load 3 rich reference sessions (Architecture Review, Clinical Operations, and Leadership Mentorship)
                  with multi-speaker transcripts, action items, and pre-anchored findings.
                </p>
              </div>
              <Button
                variant="solid"
                onClick={() => void handleSeedSample()}
                disabled={seeding}
                className="shrink-0 font-medium"
              >
                {seeding ? <Spinner className="h-3.5 w-3.5" /> : <Icon name="sparkles" className="h-3.5 w-3.5" />}
                {seeding ? "Loading Reference Library…" : "Load Reference Sample Library"}
              </Button>
            </div>

            {seedMessage && (
              <div className="rounded-lg border border-[var(--accent)]/30 bg-[var(--accent)]/10 p-3 text-[12px] text-[var(--text)]">
                {seedMessage}
              </div>
            )}

            {/* Library Import / Export */}
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-raised)] p-6 shadow-xs space-y-4">
              <h3 className="text-[14px] font-semibold">Library Backup & Import / Export</h3>
              <p className="text-[12px] text-[var(--text-faint)]">
                Export notes, transcripts, speakers, and diagnostic findings as a portable JSON package, or import an existing archive.
              </p>
              <div className="flex gap-3">
                <Button variant="outline" onClick={() => void handleExportLibrary()}>
                  <Icon name="download" className="h-3.5 w-3.5" />
                  Export Entire Library (.json)
                </Button>
                <label className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] px-3 py-1.5 text-[13px] font-medium text-[var(--text)] hover:bg-[var(--bg-raised)] cursor-pointer transition-colors">
                  <Icon name="upload" className="h-3.5 w-3.5" />
                  <span>{importingLib ? "Importing…" : "Import Library Package (.json)"}</span>
                  <input
                    type="file"
                    accept=".json"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void handleImportFile(f);
                    }}
                  />
                </label>
              </div>
              {libMessage && (
                <p className="text-[12px] text-[var(--accent)]">{libMessage}</p>
              )}
            </div>

            {/* Custom Lens Lab */}
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-raised)] p-6 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-[14px] font-semibold">Custom Lens Lab</h3>
                  <p className="text-[12px] text-[var(--text-faint)]">
                    Create, upload, and manage custom diagnostic YAML lenses without app restarts.
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => void handleDownloadSampleLens()} title="Download annotated YAML template">
                    <Icon name="download" className="h-3.5 w-3.5" />
                    Download Sample Lens Template
                  </Button>
                  <label className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] px-3 py-1.5 text-[13px] font-medium text-[var(--text)] hover:bg-[var(--bg-raised)] cursor-pointer transition-colors">
                    <Icon name="upload" className="h-3.5 w-3.5" />
                    <span>Upload YAML Lens</span>
                    <input
                      type="file"
                      accept=".yaml,.yml"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) void handleUploadLensFile(f);
                      }}
                    />
                  </label>
                  <Button
                    variant="solid"
                    onClick={() => {
                      setYamlLensName("New Custom Lens");
                      setEditingYaml(`# New Custom Lens\nid: my_custom_lens\nname: My Custom Lens\nversion: 1\ndescription: Observes custom conversational patterns\nmodel:\n  temperature: 0.15\nthresholds:\n  min_confidence: 0.65\n  max_per_chunk: 5\nguidance: |\n  Flag phrasing, never the individual.\ncategories:\n  - id: custom_pattern\n    label: Custom Pattern\n    definition: Specific phrasing to detect\n    positive_example: "Exact phrasing example"\n    negative_example: "Near-miss that does not qualify"\n`);
                    }}
                  >
                    <Icon name="plus" className="h-3.5 w-3.5" />
                    Author New Lens
                  </Button>
                </div>
              </div>

              {/* Installed Lenses Table */}
              <div className="overflow-hidden rounded-lg border border-[var(--border)]">
                <table className="w-full text-left text-[12px]">
                  <thead className="border-b border-[var(--border)] bg-[var(--bg-inset)] text-[11px] uppercase tracking-wider text-[var(--text-faint)]">
                    <tr>
                      <th className="px-3.5 py-2">Lens Name</th>
                      <th className="px-3.5 py-2">Categories</th>
                      <th className="px-3.5 py-2">Type</th>
                      <th className="px-3.5 py-2 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {lenses.map((lens) => (
                      <tr key={lens.id} className="hover:bg-[var(--bg-inset)]/40 transition-colors">
                        <td className="px-3.5 py-2.5 font-medium">
                          {lens.name}
                          <span className="block text-[11px] text-[var(--text-faint)] font-normal">
                            id: {lens.id} · v{lens.version}
                          </span>
                        </td>
                        <td className="px-3.5 py-2.5">
                          <span className="text-[var(--text-dim)]">{lens.categories.length} categories</span>
                        </td>
                        <td className="px-3.5 py-2.5">
                          {lens.builtin ? (
                            <Chip tone="accent">Built-in</Chip>
                          ) : (
                            <Chip>Custom User</Chip>
                          )}
                        </td>
                        <td className="px-3.5 py-2.5 text-right space-x-2">
                          <button
                            type="button"
                            onClick={() => void handleViewLensYaml(lens.id)}
                            className="text-[var(--accent)] hover:underline text-xs"
                          >
                            View YAML
                          </button>
                          {!lens.builtin && (
                            <button
                              type="button"
                              onClick={() => void handleDeleteLens(lens.id)}
                              className="text-[var(--bad)] hover:underline text-xs ml-2"
                            >
                              Delete
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Inline YAML Editor Modal */}
      <Modal
        isOpen={editingYaml !== null}
        onClose={() => setEditingYaml(null)}
        title={yamlLensName ? `Lens YAML: ${yamlLensName}` : "Edit Lens YAML"}
      >
        <div className="space-y-3">
          <p className="text-[12px] text-[var(--text-faint)]">
            Define categories, positive examples, and crucial near-misses (negative examples).
          </p>

          <textarea
            value={editingYaml || ""}
            onChange={(e) => setEditingYaml(e.target.value)}
            rows={18}
            className="w-full font-mono text-[12px] rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] p-3 text-[var(--text)] focus:border-[var(--accent)] focus:outline-none"
          />

          {yamlError && (
            <div className="rounded-md border border-[var(--bad)]/30 bg-[var(--bad)]/10 p-2 text-[12px] text-[var(--bad)]">
              {yamlError}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setEditingYaml(null)}>
              Cancel
            </Button>
            <Button variant="solid" onClick={() => void handleSaveCustomLens()} disabled={savingLens}>
              {savingLens ? <Spinner className="h-3.5 w-3.5" /> : null}
              {savingLens ? "Validating & Saving…" : "Validate & Save Lens"}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
