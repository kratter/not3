import { useEffect, useLayoutEffect, useState } from "react";
import { Button, Chip } from "./ui";

export interface TourStep {
  targetId: string;
  title: string;
  badge: string;
  description: string;
  actionText?: string;
  preferredPosition?: "right" | "bottom" | "top" | "left";
}

const TOUR_STEPS: TourStep[] = [
  {
    targetId: "tour-add-recording",
    badge: "Step 1 of 7",
    title: "+ Add recording Button",
    description:
      "Click this button or drag-and-drop any audio/video file (MP3, WAV, M4A, FLAC, MP4, MKV) to import it. Not3 will transcribe, diarize speakers, and run AI analysis 100% locally.",
    preferredPosition: "right",
  },
  {
    targetId: "tour-write-note",
    badge: "Step 2 of 7",
    title: "✏ Write Manual Note Button",
    description:
      "Click here to type or paste rough shorthand, doctor/clinical notes, or fragmented bullet points. Check 'Formalize with AI' to let the local model transform them into professional text.",
    preferredPosition: "right",
  },
  {
    targetId: "tour-search-bar",
    badge: "Step 3 of 7",
    title: "🔍 Search Everything Said",
    description:
      "Fast, debounced full-text search across every segment ever spoken in your library. Clicking any search hit instantly jumps the audio player to that exact word.",
    preferredPosition: "right",
  },
  {
    targetId: "tour-stage-strip",
    badge: "Step 4 of 7",
    title: "Pipeline Stage Sequence & 'export ↗'",
    description:
      "Monitors live processing: ingest → transcribe → diarize → distill → highlight → lens → export. Click the interactive 'export ↗' badge anytime to preview and copy your notes.",
    preferredPosition: "bottom",
  },
  {
    targetId: "tour-export-btn",
    badge: "Step 5 of 7",
    title: "Export & Reprocess Commands",
    description:
      "Click 'Export' to view formatted Markdown with frontmatter, copy to clipboard, or save to disk. Click 'Reprocess' to re-evaluate the note with different report styles and lenses.",
    preferredPosition: "bottom",
  },
  {
    targetId: "tour-nav-tabs",
    badge: "Step 6 of 7",
    title: "Navigation Tabs & Grounded Quotes",
    description:
      "Switch between Structured Note, Transcript with speaker tags, Highlights, and Patterns (Diagnostic Lenses). Every quote is anchored to the audio: click any quote to jump playback to that second!",
    preferredPosition: "bottom",
  },
  {
    targetId: "tour-player-bar",
    badge: "Step 7 of 7",
    title: "Timeline Audio Player",
    description:
      "Controls audio playback (Spacebar to toggle, Shift+Left/Right to skip ±5s). The timeline scrubber features color-coded tick markers showing exactly where key highlights and lens findings occurred.",
    preferredPosition: "top",
  },
];

export function InteractiveTour({
  isOpen,
  onClose,
  onEnsureNoteSelected,
}: {
  isOpen: boolean;
  onClose: () => void;
  onEnsureNoteSelected?: () => void;
}) {
  const [stepIndex, setStepIndex] = useState(0);
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);

  const currentStep = TOUR_STEPS[stepIndex] ?? TOUR_STEPS[0]!;

  // When step changes or tour opens, ensure target element is in view
  useEffect(() => {
    if (!isOpen) return;

    // Steps 3-6 require note view to be visible
    if (stepIndex >= 3 && onEnsureNoteSelected) {
      onEnsureNoteSelected();
    }
  }, [isOpen, stepIndex, onEnsureNoteSelected]);

  // Measure target element position
  const updateRect = () => {
    if (!isOpen) return;
    const el = document.getElementById(currentStep.targetId);
    if (el) {
      const r = el.getBoundingClientRect();
      setTargetRect(r);
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } else {
      // If element not found, fallback to next step if possible
      setTargetRect(null);
    }
  };

  useLayoutEffect(() => {
    updateRect();
    const timer = setTimeout(updateRect, 100);
    window.addEventListener("resize", updateRect);
    window.addEventListener("scroll", updateRect, true);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("resize", updateRect);
      window.removeEventListener("scroll", updateRect, true);
    };
  }, [isOpen, stepIndex, currentStep.targetId]);

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowRight") {
        if (stepIndex < TOUR_STEPS.length - 1) setStepIndex((i) => i + 1);
        else onClose();
      } else if (e.key === "ArrowLeft") {
        if (stepIndex > 0) setStepIndex((i) => i - 1);
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [isOpen, stepIndex, onClose]);

  if (!isOpen) return null;

  const pad = 6;
  const isFirst = stepIndex === 0;
  const isLast = stepIndex === TOUR_STEPS.length - 1;

  // Compute Popover Position relative to targetRect
  let popoverStyle: React.CSSProperties = {
    position: "fixed",
    zIndex: 102,
    maxWidth: 380,
    width: "calc(100vw - 32px)",
  };

  if (targetRect) {
    const spaceRight = window.innerWidth - targetRect.right;
    const spaceBottom = window.innerHeight - targetRect.bottom;
    const pos = currentStep.preferredPosition || "right";

    if (pos === "top" || spaceBottom < 260) {
      // Position above target
      popoverStyle = {
        ...popoverStyle,
        left: Math.max(16, Math.min(window.innerWidth - 396, targetRect.left)),
        bottom: window.innerHeight - targetRect.top + pad + 12,
      };
    } else if (pos === "right" && spaceRight >= 390) {
      // Position to right
      popoverStyle = {
        ...popoverStyle,
        left: targetRect.right + pad + 14,
        top: Math.max(16, Math.min(window.innerHeight - 280, targetRect.top - 10)),
      };
    } else {
      // Position below target
      popoverStyle = {
        ...popoverStyle,
        left: Math.max(16, Math.min(window.innerWidth - 396, targetRect.left)),
        top: targetRect.bottom + pad + 14,
      };
    }
  } else {
    // Centered fallback if element not in DOM
    popoverStyle = {
      ...popoverStyle,
      left: "50%",
      top: "50%",
      transform: "translate(-50%, -50%)",
    };
  }

  return (
    <div className="fixed inset-0 z-[100] overflow-hidden select-none animate-in fade-in duration-200">
      {/* SVG Spotlight Cutout Mask */}
      {targetRect && (
        <svg
          className="fixed inset-0 h-full w-full pointer-events-auto"
          style={{ zIndex: 100 }}
          onClick={onClose}
        >
          <defs>
            <mask id="tour-spotlight-mask">
              <rect width="100%" height="100%" fill="white" />
              <rect
                x={targetRect.left - pad}
                y={targetRect.top - pad}
                width={targetRect.width + pad * 2}
                height={targetRect.height + pad * 2}
                rx={8}
                ry={8}
                fill="black"
              />
            </mask>
          </defs>
          <rect
            width="100%"
            height="100%"
            fill="rgba(0, 0, 0, 0.65)"
            mask="url(#tour-spotlight-mask)"
          />
        </svg>
      )}

      {/* Target Element Highlighting Ring */}
      {targetRect && (
        <div
          style={{
            position: "fixed",
            left: targetRect.left - pad,
            top: targetRect.top - pad,
            width: targetRect.width + pad * 2,
            height: targetRect.height + pad * 2,
            borderRadius: 8,
            pointerEvents: "none",
            border: "2px solid var(--accent)",
            boxShadow:
              "0 0 0 4px rgba(var(--accent-rgb, 59, 130, 246), 0.35), 0 0 24px rgba(var(--accent-rgb, 59, 130, 246), 0.3)",
            zIndex: 101,
          }}
          className="transition-all duration-300"
        />
      )}

      {/* Floating Tooltip / Popover Card */}
      <div
        style={popoverStyle}
        onClick={(e) => e.stopPropagation()}
        className="rounded-xl border border-[var(--border)] bg-[var(--bg)] p-5 shadow-2xl transition-all duration-200"
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-2 border-b border-[var(--border)] pb-2.5">
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[var(--accent)] text-[10px] font-bold text-white">
              {stepIndex + 1}
            </span>
            <Chip tone="accent">{currentStep.badge}</Chip>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} title="Exit Tour (Esc)">
            ✕
          </Button>
        </div>

        {/* Title & Description */}
        <div className="my-3 space-y-1.5">
          <h3 className="text-[15px] font-bold text-[var(--text)]">
            {currentStep.title}
          </h3>
          <p className="text-[12px] leading-relaxed text-[var(--text-dim)]">
            {currentStep.description}
          </p>
        </div>

        {/* Footer Navigation */}
        <div className="flex items-center justify-between border-t border-[var(--border)] pt-3">
          <div className="flex gap-1">
            {TOUR_STEPS.map((_, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => setStepIndex(idx)}
                className={`h-1.5 rounded-full transition-all ${
                  stepIndex === idx ? "w-4 bg-[var(--accent)]" : "w-1.5 bg-[var(--border-strong)]"
                }`}
                aria-label={`Jump to step ${idx + 1}`}
              />
            ))}
          </div>

          <div className="flex items-center gap-2">
            {!isFirst && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
              >
                Back
              </Button>
            )}

            <Button
              variant="solid"
              size="sm"
              onClick={() => {
                if (!isLast) setStepIndex((i) => i + 1);
                else onClose();
              }}
            >
              {isLast ? "Done ✓" : "Next →"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
