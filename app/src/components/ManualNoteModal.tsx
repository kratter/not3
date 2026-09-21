import { useEffect, useState } from "react";

import type { Api, Lens } from "../api";
import { REPORT_STYLES } from "./ProcessOptionsModal";
import { Button, Chip, Icon, Spinner } from "./ui";

export function ManualNoteModal({
  api,
  isOpen,
  lenses = [],
  onClose,
  onCreated,
}: {
  api: Api;
  isOpen: boolean;
  lenses?: Lens[];
  onClose: () => void;
  onCreated: (noteId: number) => void;
}) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [formalize, setFormalize] = useState(true);
  const [style, setStyle] = useState("executive");
  const [loadedLenses, setLoadedLenses] = useState<Lens[]>([]);
  const [selectedLenses, setSelectedLenses] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (lenses.length === 0 && isOpen) {
      void api.lenses().then(setLoadedLenses).catch(() => undefined);
    }
  }, [api, lenses, isOpen]);

  const effectiveLenses = lenses.length > 0 ? lenses : loadedLenses;

  useEffect(() => {
    if (isOpen && effectiveLenses.length > 0 && selectedLenses.length === 0) {
      setSelectedLenses(effectiveLenses.filter((l) => l.enabled).map((l) => l.id));
    }
  }, [isOpen, effectiveLenses, selectedLenses.length]);

  if (!isOpen) return null;

  function toggleLens(id: string) {
    setSelectedLenses((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function applyPreset(preset: "all" | "psych" | "comm" | "decision" | "none") {
    if (preset === "all") {
      setSelectedLenses(effectiveLenses.map((l) => l.id));
    } else if (preset === "psych") {
      setSelectedLenses(
        effectiveLenses
          .filter((l) =>
            [
              "cognitive_distortions",
              "defense_mechanisms",
              "emotional_arc",
              "readiness_for_change",
            ].includes(l.id),
          )
          .map((l) => l.id),
      );
      setStyle("clinical");
    } else if (preset === "comm") {
      setSelectedLenses(
        effectiveLenses
          .filter((l) =>
            [
              "communication_patterns",
              "conflict_dynamics",
              "empathy_active_listening",
            ].includes(l.id),
          )
          .map((l) => l.id),
      );
      setStyle("dialogue_analysis");
    } else if (preset === "decision") {
      setSelectedLenses(
        effectiveLenses
          .filter((l) =>
            ["decision_biases", "communication_patterns"].includes(l.id),
          )
          .map((l) => l.id),
      );
      setStyle("executive");
    } else if (preset === "none") {
      setSelectedLenses([]);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;

    setError(null);
    setSubmitting(true);
    try {
      const res = await api.createTextNote({
        title: title.trim() || undefined,
        text: text.trim(),
        formalize,
        style,
        lenses: selectedLenses,
        run: true,
      });
      setTitle("");
      setText("");
      onClose();
      onCreated(res.note_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-150">
      <div
        className="w-full max-w-2xl rounded-xl border border-[var(--border)] bg-[var(--bg)] shadow-2xl overflow-hidden flex flex-col max-h-[92vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4 bg-[var(--bg-raised)]">
          <div className="flex items-center gap-2">
            <Icon name="pencil" className="h-4 w-4 text-[var(--accent)]" />
            <h2 className="text-[16px] font-semibold text-[var(--text)]">Write manual note</h2>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={submitting}>
            ✕
          </Button>
        </header>

        <form onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0 overflow-y-auto p-6 space-y-4">
          {error && (
            <div className="flex items-center gap-2 rounded-lg border border-[var(--warn)] bg-[var(--warn)]/10 px-3 py-2 text-[13px] text-[var(--warn)]">
              <Icon name="alert" className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div>
            <label className="block text-[12px] font-medium text-[var(--text-dim)] mb-1">
              Title <span className="text-[var(--text-faint)] font-normal">(optional — generated if left blank)</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Q3 Architecture Review or Patient Check-in"
              disabled={submitting}
              className="w-full rounded-md border border-[var(--border)] bg-[var(--bg-inset)] px-3 py-2 text-[14px] text-[var(--text)] placeholder:text-[var(--text-faint)] focus:border-[var(--accent)] focus:outline-none transition-colors"
            />
          </div>

          <div className="flex flex-col min-h-[140px]">
            <label className="block text-[12px] font-medium text-[var(--text-dim)] mb-1">
              Raw notes / shorthand
            </label>
            <textarea
              autoFocus
              required
              rows={6}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Enter rough shorthand, bullet points, or session notes. E.g.:&#10;- discussed migration delays&#10;- Alice: stressed about latency, insists old system was fine (denial/defensiveness)&#10;- team agreed to write action plan"
              disabled={submitting}
              className="w-full rounded-md border border-[var(--border)] bg-[var(--bg-inset)] p-3 text-[13px] font-mono leading-relaxed text-[var(--text)] placeholder:text-[var(--text-faint)] focus:border-[var(--accent)] focus:outline-none resize-y transition-colors"
            />
          </div>

          {/* AI Formalization & Report Style */}
          <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] p-4 space-y-3">
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={formalize}
                  onChange={(e) => setFormalize(e.target.checked)}
                  disabled={submitting}
                  className="rounded border-[var(--border)] text-[var(--accent)] focus:ring-0"
                />
                <span className="text-[13px] font-medium text-[var(--text)]">
                  Formalize with AI
                </span>
              </label>
              <Chip tone={formalize ? "accent" : "neutral"}>
                {formalize ? "Ollama Rewrite" : "Raw Text"}
              </Chip>
            </div>

            <div className="space-y-2 pt-2 border-t border-[var(--border)]">
              <div className="text-[11px] font-medium text-[var(--text-faint)] uppercase tracking-wider">
                Distillation & Report Style:
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {REPORT_STYLES.map((st) => {
                  const active = style === st.id;
                  return (
                    <button
                      key={st.id}
                      type="button"
                      onClick={() => setStyle(st.id)}
                      disabled={submitting}
                      className={`flex flex-col text-left rounded-lg border p-2.5 transition-colors ${
                        active
                          ? "border-[var(--accent)] bg-[var(--accent-wash)]"
                          : "border-[var(--border)] bg-[var(--bg-card)] hover:border-[var(--border-strong)]"
                      }`}
                    >
                      <span className={`text-[12px] font-medium ${active ? "text-[var(--accent)]" : "text-[var(--text)]"}`}>
                        {st.name}
                      </span>
                      <span className="text-[10px] text-[var(--text-faint)] mt-0.5 line-clamp-2">
                        {st.desc}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Diagnostic Lenses */}
          {effectiveLenses.length > 0 && (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] p-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="text-[12px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">
                    Diagnostic Lenses ({selectedLenses.length}/{effectiveLenses.length})
                  </h3>
                  <p className="text-[11px] text-[var(--text-faint)]">
                    Select lenses to identify psychological, clinical, or decision dynamics
                  </p>
                </div>
                <div className="flex flex-wrap gap-1">
                  <Button size="sm" variant="ghost" onClick={() => applyPreset("all")} className="text-[10px] h-5 px-1.5">
                    All
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => applyPreset("psych")} className="text-[10px] h-5 px-1.5">
                    Psych
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => applyPreset("comm")} className="text-[10px] h-5 px-1.5">
                    Comm
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => applyPreset("decision")} className="text-[10px] h-5 px-1.5">
                    Decisions
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => applyPreset("none")} className="text-[10px] h-5 px-1.5">
                    None
                  </Button>
                </div>
              </div>

              <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                {effectiveLenses.map((lens) => {
                  const checked = selectedLenses.includes(lens.id);
                  return (
                    <label
                      key={lens.id}
                      className={`flex cursor-pointer items-start gap-2.5 rounded-md border p-2 text-left transition-colors ${
                        checked
                          ? "border-[var(--accent)]/40 bg-[var(--accent-wash)]/15"
                          : "border-[var(--border)] bg-[var(--bg-card)] hover:border-[var(--border-strong)]"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleLens(lens.id)}
                        disabled={submitting}
                        className="mt-0.5 h-3.5 w-3.5 rounded border-[var(--border-strong)] text-[var(--accent)] focus:ring-[var(--accent)]"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[12px] font-medium text-[var(--text)]">
                            {lens.name}
                          </span>
                          {lens.categories && (
                            <span className="text-[10px] text-[var(--text-faint)]">
                              • {lens.categories.length} markers
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-[var(--text-faint)] line-clamp-1">
                          {lens.description}
                        </p>
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-[var(--border)]">
            <Button variant="ghost" onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button
              variant="solid"
              type="submit"
              disabled={submitting || !text.trim()}
            >
              {submitting ? <Spinner /> : <Icon name="pencil" className="h-3.5 w-3.5" />}
              {submitting ? (formalize ? "Formalizing…" : "Processing…") : "Save & Process"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
