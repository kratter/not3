import { useState } from "react";

import type { Api } from "../api";
import { Button, Chip, Icon, Spinner } from "./ui";

export function ManualNoteModal({
  api,
  isOpen,
  onClose,
  onCreated,
}: {
  api: Api;
  isOpen: boolean;
  onClose: () => void;
  onCreated: (noteId: number) => void;
}) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [formalize, setFormalize] = useState(true);
  const [style, setStyle] = useState<"formal" | "technical" | "bullet_structured">("formal");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

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
              placeholder="e.g. Q3 Architecture Review"
              disabled={submitting}
              className="w-full rounded-md border border-[var(--border)] bg-[var(--bg-inset)] px-3 py-2 text-[14px] text-[var(--text)] placeholder:text-[var(--text-faint)] focus:border-[var(--accent)] focus:outline-none transition-colors"
            />
          </div>

          <div className="flex-1 flex flex-col min-h-[160px]">
            <label className="block text-[12px] font-medium text-[var(--text-dim)] mb-1">
              Raw notes / shorthand
            </label>
            <textarea
              autoFocus
              required
              rows={8}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Enter rough shorthand, bullet points, or notes. E.g.:&#10;- discuss Q3 migration&#10;- Alice: database latency dropped 40%&#10;- Bob will prepare RFC by Friday"
              disabled={submitting}
              className="w-full flex-1 min-h-[160px] rounded-md border border-[var(--border)] bg-[var(--bg-inset)] p-3 text-[13px] font-mono leading-relaxed text-[var(--text)] placeholder:text-[var(--text-faint)] focus:border-[var(--accent)] focus:outline-none resize-y transition-colors"
            />
          </div>

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

            {formalize && (
              <div className="space-y-2 pt-1 border-t border-[var(--border)]">
                <div className="text-[11px] text-[var(--text-faint)]">
                  Tone & style:
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setStyle("formal")}
                    disabled={submitting}
                    className={`px-3 py-1 text-[12px] rounded-md border transition-colors ${
                      style === "formal"
                        ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)] font-medium"
                        : "border-[var(--border)] text-[var(--text-dim)] hover:border-[var(--text-faint)]"
                    }`}
                  >
                    Executive / Formal
                  </button>
                  <button
                    type="button"
                    onClick={() => setStyle("technical")}
                    disabled={submitting}
                    className={`px-3 py-1 text-[12px] rounded-md border transition-colors ${
                      style === "technical"
                        ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)] font-medium"
                        : "border-[var(--border)] text-[var(--text-dim)] hover:border-[var(--text-faint)]"
                    }`}
                  >
                    Technical
                  </button>
                  <button
                    type="button"
                    onClick={() => setStyle("bullet_structured")}
                    disabled={submitting}
                    className={`px-3 py-1 text-[12px] rounded-md border transition-colors ${
                      style === "bullet_structured"
                        ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)] font-medium"
                        : "border-[var(--border)] text-[var(--text-dim)] hover:border-[var(--text-faint)]"
                    }`}
                  >
                    Structured Bullets
                  </button>
                </div>
                <p className="text-[11px] leading-normal text-[var(--text-faint)] pt-1">
                  Transforms fragmented phrases and abbreviations into professional language, preserves all facts and quotes, and feeds segments to distillation and pattern lenses.
                </p>
              </div>
            )}
          </div>

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
