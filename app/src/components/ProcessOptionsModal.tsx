import { useState } from "react";
import type { Lens } from "../api";
import { Button, Chip } from "./ui";

export interface ProcessOptions {
  style: string;
  lenses: string[];
}

export const REPORT_STYLES = [
  {
    id: "executive",
    name: "Executive & Strategic",
    desc: "Decisive executive overview, high-level commitments, and strategic takeaways.",
  },
  {
    id: "clinical",
    name: "Clinical & Psychological",
    desc: "Observational presentation, cognitive themes, affective tone, and verbatim evidence.",
  },
  {
    id: "technical",
    name: "Technical & Architectural",
    desc: "Precise engineering documentation, system specs, constraints, and trade-offs.",
  },
  {
    id: "bullet_structured",
    name: "Structured Action Matrix",
    desc: "High-density hierarchical bullet points, structured decisions, and ownership.",
  },
  {
    id: "dialogue_analysis",
    name: "Dialogue & Conversational Flow",
    desc: "Speaker alignment, bids for connection, points of consensus, and friction.",
  },
];

export function ProcessOptionsModal({
  title = "Process Options",
  subtitle,
  lenses,
  initialStyle = "executive",
  onConfirm,
  onClose,
}: {
  title?: string;
  subtitle?: string;
  lenses: Lens[];
  initialStyle?: string;
  onConfirm: (opts: ProcessOptions) => void;
  onClose: () => void;
}) {
  const [selectedStyle, setSelectedStyle] = useState(initialStyle);
  const [selectedLenses, setSelectedLenses] = useState<string[]>(
    lenses.filter((l) => l.enabled).map((l) => l.id),
  );

  function toggleLens(id: string) {
    setSelectedLenses((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function applyPreset(preset: "all" | "psych" | "comm" | "decision" | "none") {
    if (preset === "all") {
      setSelectedLenses(lenses.map((l) => l.id));
    } else if (preset === "psych") {
      setSelectedLenses(
        lenses
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
      setSelectedStyle("clinical");
    } else if (preset === "comm") {
      setSelectedLenses(
        lenses
          .filter((l) =>
            [
              "communication_patterns",
              "conflict_dynamics",
              "empathy_active_listening",
            ].includes(l.id),
          )
          .map((l) => l.id),
      );
      setSelectedStyle("dialogue_analysis");
    } else if (preset === "decision") {
      setSelectedLenses(
        lenses
          .filter((l) =>
            ["decision_biases", "communication_patterns"].includes(l.id),
          )
          .map((l) => l.id),
      );
      setSelectedStyle("executive");
    } else if (preset === "none") {
      setSelectedLenses([]);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-xl border border-[var(--border)] bg-[var(--bg)] shadow-2xl">
        <header className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
          <div>
            <h2 className="text-[16px] font-semibold text-[var(--text)]">{title}</h2>
            {subtitle && (
              <p className="truncate max-w-lg text-[12px] text-[var(--text-faint)]">
                {subtitle}
              </p>
            )}
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            ✕
          </Button>
        </header>

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Section 1: Report Style */}
          <section>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-[13px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">
                Analysis & Report Style
              </h3>
              <span className="text-[11px] text-[var(--text-faint)]">
                Shapes summaries, distillation & formatting
              </span>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {REPORT_STYLES.map((style) => {
                const active = selectedStyle === style.id;
                return (
                  <button
                    key={style.id}
                    type="button"
                    onClick={() => setSelectedStyle(style.id)}
                    className={`flex flex-col text-left rounded-lg border p-3 transition-all ${
                      active
                        ? "border-[var(--accent)] bg-[var(--accent-wash)]"
                        : "border-[var(--border)] bg-[var(--bg-card)] hover:border-[var(--border-strong)]"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span
                        className={`text-[13px] font-medium ${
                          active ? "text-[var(--accent)]" : "text-[var(--text)]"
                        }`}
                      >
                        {style.name}
                      </span>
                      {active && (
                        <span className="h-2 w-2 rounded-full bg-[var(--accent)]" />
                      )}
                    </div>
                    <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-faint)]">
                      {style.desc}
                    </p>
                  </button>
                );
              })}
            </div>
          </section>

          {/* Section 2: Diagnoses & Lenses */}
          <section>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-[13px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">
                  Diagnostic Lenses & Patterns
                </h3>
                <p className="text-[11px] text-[var(--text-faint)]">
                  Select which lenses will evaluate the verbatim transcript
                </p>
              </div>
              {/* Presets */}
              <div className="flex flex-wrap gap-1">
                <Button size="sm" variant="ghost" onClick={() => applyPreset("all")} className="text-[11px] h-6 px-2">
                  All ({lenses.length})
                </Button>
                <Button size="sm" variant="ghost" onClick={() => applyPreset("psych")} className="text-[11px] h-6 px-2">
                  Psychological
                </Button>
                <Button size="sm" variant="ghost" onClick={() => applyPreset("comm")} className="text-[11px] h-6 px-2">
                  Communication
                </Button>
                <Button size="sm" variant="ghost" onClick={() => applyPreset("decision")} className="text-[11px] h-6 px-2">
                  Decisions
                </Button>
                <Button size="sm" variant="ghost" onClick={() => applyPreset("none")} className="text-[11px] h-6 px-2">
                  None
                </Button>
              </div>
            </div>

            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {lenses.map((lens) => {
                const checked = selectedLenses.includes(lens.id);
                return (
                  <label
                    key={lens.id}
                    className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors ${
                      checked
                        ? "border-[var(--accent)]/40 bg-[var(--accent-wash)]/20"
                        : "border-[var(--border)] bg-[var(--bg-card)] hover:border-[var(--border-strong)]"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleLens(lens.id)}
                      className="mt-1 h-4 w-4 rounded border-[var(--border-strong)] text-[var(--accent)] focus:ring-[var(--accent)]"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[13px] font-medium text-[var(--text)]">
                          {lens.name}
                        </span>
                        {lens.categories && (
                          <Chip tone="neutral">
                            {lens.categories.length} categories
                          </Chip>
                        )}
                      </div>
                      <p className="mt-0.5 text-[12px] leading-relaxed text-[var(--text-faint)]">
                        {lens.description}
                      </p>
                    </div>
                  </label>
                );
              })}
            </div>
          </section>
        </div>

        <footer className="flex items-center justify-between border-t border-[var(--border)] px-6 py-4">
          <div className="text-[12px] text-[var(--text-faint)]">
            <span>
              {selectedLenses.length} of {lenses.length} lenses selected
            </span>
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="solid"
              onClick={() => {
                onConfirm({
                  style: selectedStyle,
                  lenses: selectedLenses,
                });
              }}
            >
              Start Processing
            </Button>
          </div>
        </footer>
      </div>
    </div>
  );
}
