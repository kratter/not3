import { useState, useEffect, useRef } from "react";
import type { Api } from "../api";
import { Spinner } from "./ui";

const TEMPLATES = [
  {
    name: "+ Clinician Observations",
    content: "### Clinician Observations\n- Affect & Demeanor: \n- Non-verbal cues: \n- Interactional dynamics: \n",
  },
  {
    name: "+ Follow-up Checklist",
    content: "### Follow-up Tasks\n- [ ] Review lab work / collateral history\n- [ ] Send summary to client / team\n- [ ] Schedule follow-up appointment\n",
  },
  {
    name: "+ Diagnostic Reflections",
    content: "### Diagnostic Reflections & Hypotheses\n- Working diagnosis / primary impressions: \n- Rule-outs / differentials: \n- Treatment response: \n",
  },
];

export function PlusNotes({
  api,
  noteId,
  initialContent = "",
  onChanged,
}: {
  api: Api;
  noteId: number;
  initialContent?: string;
  onChanged?: () => void;
}) {
  const [content, setContent] = useState(initialContent);
  const [saving, setSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [preview, setPreview] = useState(false);
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);


  useEffect(() => {
    setContent(initialContent);
  }, [noteId, initialContent]);

  function handleChange(nextText: string) {
    setContent(nextText);
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(() => {
      void save(nextText);
    }, 800);
  }

  async function save(textToSave: string) {
    setSaving(true);
    try {
      await api.savePlusNotes(noteId, textToSave);
      setLastSaved(new Date());
      onChanged?.();
    } finally {
      setSaving(false);
    }
  }

  function insertTemplate(tplText: string) {
    const updated = content ? `${content.trim()}\n\n${tplText}` : tplText;
    handleChange(updated);
  }

  const wordCount = content.trim() ? content.trim().split(/\s+/).length : 0;
  const charCount = content.length;

  return (
    <div className="flex h-full flex-col bg-[var(--bg)]">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between border-b border-[var(--border)] px-6 py-2.5 gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded bg-[var(--accent)]/15 text-[var(--accent)] text-[12px] font-bold">
            +
          </span>
          <span className="text-[13px] font-semibold text-[var(--text)]">Plus Notes</span>
          <span className="text-[11px] text-[var(--text-faint)]">
            (Supplementary addenda, clinical notes, and private scratchpad)
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-faint)]">
            {saving ? (
              <span className="flex items-center gap-1 text-[var(--accent)]">
                <Spinner className="h-3 w-3" />
                Saving...
              </span>
            ) : lastSaved ? (
              <span>Saved at {lastSaved.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
            ) : (
              <span>All changes saved</span>
            )}
          </div>

          <div className="flex items-center rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] p-0.5">
            <button
              type="button"
              onClick={() => setPreview(false)}
              className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors ${
                !preview
                  ? "bg-[var(--bg-raised)] text-[var(--text)] shadow-sm"
                  : "text-[var(--text-faint)] hover:text-[var(--text)]"
              }`}
            >
              Write
            </button>
            <button
              type="button"
              onClick={() => setPreview(true)}
              className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors ${
                preview
                  ? "bg-[var(--bg-raised)] text-[var(--text)] shadow-sm"
                  : "text-[var(--text-faint)] hover:text-[var(--text)]"
              }`}
            >
              Preview
            </button>
          </div>
        </div>
      </div>

      {/* Quick Insert Templates bar */}
      <div className="flex items-center gap-1.5 overflow-x-auto border-b border-[var(--border)]/50 bg-[var(--bg-raised)]/30 px-6 py-2">
        <span className="text-[10px] uppercase tracking-wider text-[var(--text-faint)] shrink-0 mr-1">
          Insert:
        </span>
        {TEMPLATES.map((tpl) => (
          <button
            key={tpl.name}
            type="button"
            onClick={() => insertTemplate(tpl.content)}
            className="shrink-0 rounded-full border border-[var(--border)] bg-[var(--bg)] px-2.5 py-0.5 text-[11px] text-[var(--text-dim)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            {tpl.name}
          </button>
        ))}
      </div>

      {/* Editor / Preview Area */}
      <div className="min-h-0 flex-1 p-6 overflow-y-auto">
        {preview ? (
          <div className="max-w-3xl prose prose-sm dark:prose-invert">
            {content ? (
              <div className="whitespace-pre-wrap text-[14px] leading-relaxed text-[var(--text)] font-sans">
                {content}
              </div>
            ) : (
              <p className="italic text-[var(--text-faint)]">No content yet. Switch to Write to add notes.</p>
            )}
          </div>
        ) : (
          <textarea
            value={content}
            onChange={(e) => handleChange(e.target.value)}
            placeholder="Type your supplementary notes, personal reflections, clinical addendum, or follow-ups here... (Markdown supported, auto-saved)"
            className="h-full w-full max-w-3xl resize-none rounded-xl border border-[var(--border)] bg-[var(--bg-inset)] p-4 text-[14px] leading-relaxed text-[var(--text)] placeholder-[var(--text-faint)] focus:border-[var(--accent)] focus:outline-none font-mono"
          />
        )}
      </div>

      {/* Footer Status */}
      <div className="flex items-center justify-between border-t border-[var(--border)] px-6 py-2 text-[11px] text-[var(--text-faint)]">
        <span>Markdown supported • Included in Note Export</span>
        <div className="flex gap-3">
          <span>{wordCount} words</span>
          <span>{charCount} characters</span>
        </div>
      </div>
    </div>
  );
}
