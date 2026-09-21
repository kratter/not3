import { useState, useRef, useEffect } from "react";
import type { Api } from "../api";
import { Button, Chip, Icon, Spinner } from "./ui";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

const QUICK_ACTIONS = [
  {
    label: "📝 Executive Summary",
    prompt:
      "Reformat this note into a high-level executive briefing with core objectives, key takeaways, and strategic implications.",
  },
  {
    label: "📋 Action & Decisions",
    prompt:
      "Extract all definitive decisions, owners, and immediate next actions from this conversation into a clean action log.",
  },
  {
    label: "🩺 Clinical SOAP",
    prompt:
      "Structure this session into formal SOAP format: Subjective (client verbatim quotes & themes), Objective (observed patterns), Assessment (synthesis), Plan (next steps).",
  },
  {
    label: "🎯 Crisp Bullets",
    prompt:
      "Convert this note into concise, punchy bullet points grouped by topic, eliminating conversational filler.",
  },
  {
    label: "✨ Polish Speech",
    prompt:
      "Rewrite and polish the note summary in formal, professional language, smoothing out speech disfluencies.",
  },
];

export function NoteChat({
  api,
  noteId,
  noteTitle,
  onSectionUpdated,
  onPlusNotesUpdated,
}: {
  api: Api;
  noteId: number;
  noteTitle: string;
  onSectionUpdated?: (kind: string, text: string) => void;
  onPlusNotesUpdated?: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend(promptText?: string) {
    const text = (promptText ?? input).trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = {
      id: String(Date.now()),
      role: "user",
      content: text,
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!promptText) setInput("");
    setLoading(true);

    try {
      const history = messages.map((m) => ({ role: m.role, content: m.content }));
      const res = await api.noteChat(noteId, text, history);

      const assistantMsg: ChatMessage = {
        id: String(Date.now() + 1),
        role: "assistant",
        content: res.reply,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: unknown) {
      const errorMsg: ChatMessage = {
        id: String(Date.now() + 1),
        role: "assistant",
        content: `Error: ${String(err instanceof Error ? err.message : err)}`,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  }

  async function applyToSection(kind: string, content: string) {
    try {
      await api.updateNoteSection(noteId, kind, content);
      onSectionUpdated?.(kind, content);
      setActionFeedback(`Updated Note ${kind.replace("_", " ")}!`);
      setTimeout(() => setActionFeedback(null), 3000);
    } catch (err: unknown) {
      setActionFeedback(`Failed to update section: ${String(err)}`);
      setTimeout(() => setActionFeedback(null), 4000);
    }
  }

  async function appendToPlusNotes(content: string) {
    try {
      const existing = await api.getPlusNotes(noteId);
      const combined = existing.plus_notes
        ? `${existing.plus_notes}\n\n### AI Reformat\n${content}`
        : `### AI Reformat\n${content}`;
      await api.savePlusNotes(noteId, combined);
      onPlusNotesUpdated?.();
      setActionFeedback("Appended to Plus Notes!");
      setTimeout(() => setActionFeedback(null), 3000);
    } catch (err: unknown) {
      setActionFeedback(`Failed to append: ${String(err)}`);
      setTimeout(() => setActionFeedback(null), 4000);
    }
  }

  async function copyContent(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setActionFeedback("Copied to clipboard!");
      setTimeout(() => setActionFeedback(null), 2500);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="flex h-full flex-col bg-[var(--bg)]">
      {/* Header bar */}
      <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-[var(--accent)]/15 text-[var(--accent)] text-[13px]">
            ✨
          </span>
          <div>
            <h3 className="text-[13px] font-semibold text-[var(--text)]">AI Chat & Reformat</h3>
            <p className="text-[11px] text-[var(--text-faint)]">
              Ask questions or reformat {noteTitle} using local Ollama
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {actionFeedback && (
            <Chip tone="good">
              {actionFeedback}
            </Chip>
          )}
          {messages.length > 0 && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setMessages([])}
              className="text-[11px] text-[var(--text-faint)]"
            >
              Clear Chat
            </Button>
          )}
        </div>
      </div>

      {/* Messages area */}
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--bg-raised)] text-[22px] shadow-sm ring-1 ring-[var(--border)]">
              ✨
            </div>
            <h4 className="text-[14px] font-semibold text-[var(--text)]">Reformat or Chat with Note</h4>
            <p className="mt-1 max-w-md text-[12px] leading-relaxed text-[var(--text-faint)]">
              Choose a quick reformat preset below, or ask any question to restructure the note content.
            </p>

            <div className="mt-6 flex max-w-lg flex-wrap justify-center gap-2">
              {QUICK_ACTIONS.map((action) => (
                <button
                  key={action.label}
                  type="button"
                  onClick={() => handleSend(action.prompt)}
                  className="flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--bg-raised)] px-3 py-1.5 text-[12px] font-medium text-[var(--text-dim)] shadow-sm hover:border-[var(--accent)] hover:text-[var(--accent)] hover:bg-[var(--accent)]/5 transition-all"
                >
                  {action.label}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-[13px] leading-relaxed shadow-sm ${
                  m.role === "user"
                    ? "bg-[var(--accent)] text-white font-medium rounded-br-none"
                    : "border border-[var(--border)] bg-[var(--bg-raised)] text-[var(--text)] rounded-bl-none whitespace-pre-wrap font-sans"
                }`}
              >
                {m.content}
              </div>

              {/* Action bar for assistant responses */}
              {m.role === "assistant" && (
                <div className="mt-1.5 flex flex-wrap items-center gap-1 text-[11px]">
                  <button
                    type="button"
                    onClick={() => copyContent(m.content)}
                    className="flex items-center gap-1 rounded px-2 py-0.5 text-[var(--text-faint)] hover:bg-[var(--bg-inset)] hover:text-[var(--text)]"
                    title="Copy response"
                  >
                    <Icon name="copy" className="h-3 w-3" />
                    Copy
                  </button>
                  <span className="text-[var(--border-strong)]">|</span>
                  <button
                    type="button"
                    onClick={() => applyToSection("summary", m.content)}
                    className="rounded px-2 py-0.5 text-[var(--accent)] hover:bg-[var(--accent)]/10 font-medium"
                    title="Apply directly to Note Summary"
                  >
                    ↳ Apply to Summary
                  </button>
                  <button
                    type="button"
                    onClick={() => applyToSection("key_points", m.content)}
                    className="rounded px-2 py-0.5 text-[var(--text-dim)] hover:bg-[var(--bg-inset)]"
                    title="Apply to Key Points"
                  >
                    ↳ Key Points
                  </button>
                  <button
                    type="button"
                    onClick={() => appendToPlusNotes(m.content)}
                    className="rounded px-2 py-0.5 text-[var(--text-dim)] hover:bg-[var(--bg-inset)]"
                    title="Save into Plus Notes"
                  >
                    ↳ Plus Notes
                  </button>
                </div>
              )}
            </div>
          ))
        )}

        {loading && (
          <div className="flex items-center gap-2 text-[12px] text-[var(--text-faint)]">
            <Spinner className="h-3.5 w-3.5 text-[var(--accent)]" />
            <span>Ollama is crafting reformatted response...</span>
          </div>
        )}
        <div ref={scrollRef} />
      </div>

      {/* Preset pills when chatting */}
      {messages.length > 0 && (
        <div className="flex items-center gap-1.5 overflow-x-auto border-t border-[var(--border)]/50 bg-[var(--bg-raised)]/40 px-6 py-2">
          <span className="text-[10px] uppercase tracking-wider text-[var(--text-faint)] shrink-0 mr-1">
            Quick:
          </span>
          {QUICK_ACTIONS.map((action) => (
            <button
              key={action.label}
              type="button"
              disabled={loading}
              onClick={() => handleSend(action.prompt)}
              className="shrink-0 rounded-full border border-[var(--border)] bg-[var(--bg)] px-2.5 py-0.5 text-[11px] text-[var(--text-dim)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
            >
              {action.label}
            </button>
          ))}
        </div>
      )}

      {/* Input bar */}
      <div className="border-t border-[var(--border)] bg-[var(--bg-raised)] px-6 py-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type reformat instruction (e.g. 'rewrite in 3 bullet points' or 'format as SOAP note')..."
            disabled={loading}
            className="flex-1 rounded-xl border border-[var(--border)] bg-[var(--bg-inset)] px-4 py-2 text-[13px] text-[var(--text)] placeholder-[var(--text-faint)] focus:border-[var(--accent)] focus:outline-none"
          />
          <Button
            type="submit"
            variant="solid"
            disabled={loading || !input.trim()}
            className="rounded-xl px-4 py-2"
          >
            {loading ? <Spinner className="h-3.5 w-3.5" /> : "Send"}
          </Button>
        </form>
      </div>
    </div>
  );
}
