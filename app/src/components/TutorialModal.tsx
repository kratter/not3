import { useState } from "react";
import { Button, Chip, Icon } from "./ui";

interface ButtonCallout {
  label: string;
  action: string;
  description: string;
}

interface StepInfo {
  number: number;
  title: string;
  badge: string;
  image: string;
  summary: string;
  callouts: ButtonCallout[];
  tips: string;
}

const TUTORIAL_STEPS: StepInfo[] = [
  {
    number: 1,
    title: "Sidebar Controls: Ingest & Navigation",
    badge: "Interface Guide",
    image: "/tut_sidebar_controls.jpg",
    summary: "Control center for adding audio recordings, creating manual shorthand notes, and searching your library.",
    callouts: [
      {
        label: "+ Add recording",
        action: "File Picker Dialog",
        description: "Opens system file dialog to select audio/video (MP3, WAV, M4A, FLAC, MP4, etc.). Starts local speech-to-text.",
      },
      {
        label: "✏ Write",
        action: "Manual Shorthand Composer",
        description: "Opens composer to paste quick notes, abbreviations, or rough bullets. AI formalization turns them into clean notes.",
      },
      {
        label: "🔍 Search everything said",
        action: "Instant Full-Text Search",
        description: "Debounced real-time search across every word ever spoken in your library. Clicking a hit jumps audio to that second.",
      },
      {
        label: "Note List & Status Badges",
        action: "Library Browser",
        description: "Select any note to inspect its analysis. Status chips indicate whether a note is processing or ready.",
      },
      {
        label: "⚙ Settings & ✨ Tutorial",
        action: "Configuration & Help",
        description: "Access component verification, transcription engine selection, model configuration, theme toggle, or reopen this guide.",
      },
    ],
    tips: "Drag-and-drop any audio or video file directly into the sidebar to start importing immediately.",
  },
  {
    number: 2,
    title: "Pre-Processing Choices: Styles & Lenses",
    badge: "Analysis Setup",
    image: "/tut_options_lenses.jpg",
    summary: "Configure the distillation perspective and choose which diagnostic lenses evaluate the transcript.",
    callouts: [
      {
        label: "1. Report Style Selector",
        action: "Tone & Structure Choice",
        description: "Choose Executive & Strategic, Clinical & Psychological, Technical & Architectural, Structured Matrix, or Dialogue Flow.",
      },
      {
        label: "2. Presets: All | Psych | Comm | Decisions | None",
        action: "One-Click Filter Sets",
        description: "Quickly select curated diagnostic lens suites (e.g. 'Psych' activates defense mechanisms and cognitive distortions).",
      },
      {
        label: "3. Diagnostic Lenses Checklist",
        action: "Granular Pattern Selection",
        description: "Toggle individual lenses: Cognitive Distortions, Defense Mechanisms, Conflict Dynamics, Empathy, Decision Biases, and more.",
      },
      {
        label: "4. Start Processing Button",
        action: "Submit & Queue Note",
        description: "Submits chosen configuration to the local pipeline. Only selected lenses will run, saving compute and time.",
      },
    ],
    tips: "You can click 'Reprocess Note' on any existing note to re-run the pipeline with a different report style or lens set anytime.",
  },
  {
    number: 3,
    title: "Note View & Interactive Timeline Player",
    badge: "Inspection & Playback",
    image: "/tut_noteview_player.jpg",
    summary: "Inspect structured outputs, read speaker-attributed transcripts, and listen to verbatim audio evidence.",
    callouts: [
      {
        label: "1. Header Actions (Reprocess & Export)",
        action: "Toolbar Commands",
        description: "'Reprocess' re-evaluates note with different lenses. 'Export' opens live markdown preview with copy & save options.",
      },
      {
        label: "2. Stage Sequence Strip with 'export ↗'",
        action: "Pipeline Monitor",
        description: "Displays live progress through ingest, transcribe, diarize, distill, highlight, lens, and export. Click 'export ↗' to view export.",
      },
      {
        label: "3. Navigation Tabs",
        action: "View Switching",
        description: "Switch between 'Structured Note' (summary/actions), 'Transcript' (timecoded text), 'Highlights', and 'Lenses' (findings).",
      },
      {
        label: "4. Verbatim Quote Anchoring",
        action: "Interactive Quote Scrubbing",
        description: "Every highlight and lens finding carries a verbatim quote. Clicking any quote jumps playback directly to that moment.",
      },
      {
        label: "5. Bottom Timeline Player Bar",
        action: "Audio Transport & Markers",
        description: "Features play/pause, timecode display, and colored tick marks along the scrubber indicating key highlights.",
      },
    ],
    tips: "Press Spacebar anywhere to play/pause audio, and Shift+Left/Right Arrow to skip 5 seconds backward/forward.",
  },
  {
    number: 4,
    title: "Export & Knowledge Base Integration",
    badge: "Output & Sharing",
    image: "/workflow_tutorial.jpg",
    summary: "Generate clean, portable Markdown notes with YAML frontmatter ready for Obsidian, Notion, or git.",
    callouts: [
      {
        label: "Copy to Clipboard",
        action: "Instant Clipboard Paste",
        description: "Copies the complete formatted Markdown note to your clipboard for instant pasting into Slack, Notion, or emails.",
      },
      {
        label: "Export to File",
        action: "Save Markdown Document",
        description: "Writes the note to your local exports folder (%LOCALAPPDATA%\\Not3\\export\\). Never overwrites without confirmation.",
      },
      {
        label: "Obsidian & Logseq Ready",
        action: "Second Brain Compatibility",
        description: "Includes YAML frontmatter with title, date, duration, speaker list, tags, and clickable timestamps.",
      },
    ],
    tips: "All notes and audio remain 100% on your local machine. No cloud API or subscription is ever required.",
  },
];

export function TutorialModal({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const [activeStep, setActiveStep] = useState(0);

  if (!isOpen) return null;

  const current = TUTORIAL_STEPS[activeStep] ?? TUTORIAL_STEPS[0]!;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-md animate-in fade-in duration-200">
      <div
        className="flex max-h-[92vh] w-full max-w-3xl flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg)] shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <header className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4 bg-[var(--bg-raised)]">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--accent)]/15 text-[var(--accent)]">
              <Icon name="sparkles" className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-[17px] font-semibold text-[var(--text)]">Not3 Visual Interface Guide</h2>
              <p className="text-[12px] text-[var(--text-faint)]">
                Schematic walkthrough of all buttons, choices, and functions
              </p>
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            ✕
          </Button>
        </header>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Step Selector Tabs */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {TUTORIAL_STEPS.map((step, idx) => {
              const isSelected = activeStep === idx;
              return (
                <button
                  key={step.number}
                  type="button"
                  onClick={() => setActiveStep(idx)}
                  className={`flex flex-col rounded-lg border p-2 text-left transition-all ${
                    isSelected
                      ? "border-[var(--accent)] bg-[var(--accent-wash)] shadow-sm"
                      : "border-[var(--border)] bg-[var(--bg-card)] hover:border-[var(--border-strong)]"
                  }`}
                >
                  <span
                    className={`text-[10px] font-semibold uppercase tracking-wider ${
                      isSelected ? "text-[var(--accent)]" : "text-[var(--text-faint)]"
                    }`}
                  >
                    Step {step.number}
                  </span>
                  <span
                    className={`mt-0.5 truncate text-[12px] font-medium ${
                      isSelected ? "text-[var(--accent)]" : "text-[var(--text)]"
                    }`}
                  >
                    {step.title.split(":")[0]}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Minimal Schematic Diagram with Callouts */}
          <div className="relative overflow-hidden rounded-xl border border-[var(--border)] bg-white p-2 shadow-sm">
            <img
              src={current.image}
              alt={current.title}
              className="w-full h-auto object-contain max-h-[290px] rounded-lg select-none"
            />
          </div>

          {/* Active Step Content */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-4 space-y-3.5">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] pb-2.5">
              <div>
                <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--accent)]">
                  Step {current.number} of {TUTORIAL_STEPS.length}
                </span>
                <h3 className="text-[15px] font-bold text-[var(--text)]">{current.title}</h3>
              </div>
              <Chip tone="accent">{current.badge}</Chip>
            </div>

            <p className="text-[12px] text-[var(--text-dim)] leading-relaxed">
              {current.summary}
            </p>

            {/* Button Callout Reference Cards */}
            <div className="space-y-2">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">
                Button & Choice Reference:
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {current.callouts.map((callout, cIdx) => (
                  <div
                    key={cIdx}
                    className="rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] p-2.5 text-left transition-colors hover:border-[var(--border-strong)]"
                  >
                    <div className="flex items-center justify-between gap-1.5">
                      <span className="font-mono text-[12px] font-semibold text-[var(--accent)]">
                        {callout.label}
                      </span>
                      <span className="text-[10px] text-[var(--text-faint)] truncate max-w-[120px]">
                        {callout.action}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-dim)]">
                      {callout.description}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            {/* Pro Tip Box */}
            <div className="flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] px-3 py-2 text-[11px] text-[var(--text-faint)]">
              <Icon name="sparkles" className="h-3.5 w-3.5 shrink-0 text-[var(--accent)]" />
              <span>
                <strong className="text-[var(--text)]">Pro Tip:</strong> {current.tips}
              </span>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <footer className="flex items-center justify-between border-t border-[var(--border)] px-6 py-3.5 bg-[var(--bg-raised)]">
          <div className="flex gap-1.5">
            {TUTORIAL_STEPS.map((_, dotIdx) => (
              <button
                key={dotIdx}
                type="button"
                onClick={() => setActiveStep(dotIdx)}
                className={`h-2 rounded-full transition-all ${
                  activeStep === dotIdx ? "w-6 bg-[var(--accent)]" : "w-2 bg-[var(--border-strong)]"
                }`}
                aria-label={`Go to step ${dotIdx + 1}`}
              />
            ))}
          </div>

          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={activeStep === 0}
              onClick={() => setActiveStep((prev) => Math.max(0, prev - 1))}
            >
              Previous
            </Button>

            {activeStep < TUTORIAL_STEPS.length - 1 ? (
              <Button
                variant="solid"
                size="sm"
                onClick={() => setActiveStep((prev) => Math.min(TUTORIAL_STEPS.length - 1, prev + 1))}
              >
                Next Step
              </Button>
            ) : (
              <Button variant="solid" size="sm" onClick={onClose}>
                Got it, let&apos;s start!
              </Button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}
