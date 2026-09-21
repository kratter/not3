import { useState } from "react";
import type { Api, NoteComment } from "../api";
import type { Player as PlayerState } from "../hooks";
import { duration } from "../util";
import { Button, Empty, Spinner } from "./ui";

export function NoteComments({
  api,
  noteId,
  comments,
  player,
  onCommentsChanged,
}: {
  api: Api;
  noteId: number;
  comments: NoteComment[];
  player: PlayerState;
  onCommentsChanged: () => void;
}) {
  const [content, setContent] = useState("");
  const [author, setAuthor] = useState("User");
  const [tagCurrentTime, setTagCurrentTime] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const currentPlayMs = Math.round(player.currentMs);


  async function handleAddComment(e: React.FormEvent) {
    e.preventDefault();
    if (!content.trim() || submitting) return;

    setSubmitting(true);
    try {
      await api.addComment(noteId, {
        content: content.trim(),
        author: author.trim() || "User",
        timestamp_ms: tagCurrentTime && currentPlayMs > 0 ? currentPlayMs : null,
      });
      setContent("");
      onCommentsChanged();
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeleteComment(commentId: number) {
    setDeletingId(commentId);
    try {
      await api.deleteComment(noteId, commentId);
      onCommentsChanged();
    } finally {
      setDeletingId(null);
    }
  }

  function jumpToTime(ms: number) {
    player.seek(ms);
    player.play();
  }


  return (
    <div className="flex h-full flex-col bg-[var(--bg)]">
      {/* Comments List */}
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5 space-y-4">
        {comments.length === 0 ? (
          <Empty
            title="No comments yet"
            hint="Add comments, observations, or audio-timestamped review notes for this session below."
          />
        ) : (
          <div className="max-w-2xl space-y-3">
            {comments.map((c) => (
              <div
                key={c.id}
                className="group relative rounded-xl border border-[var(--border)] bg-[var(--bg-raised)] p-4 shadow-sm hover:border-[var(--border-strong)] transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--accent)]/15 text-[11px] font-semibold text-[var(--accent)]">
                      {c.author.charAt(0).toUpperCase()}
                    </span>
                    <span className="text-[13px] font-medium text-[var(--text)]">
                      {c.author}
                    </span>
                    {c.timestamp_ms != null && (
                      <button
                        type="button"
                        onClick={() => jumpToTime(c.timestamp_ms!)}
                        className="flex items-center gap-1 rounded-full bg-[var(--accent)]/10 px-2 py-0.5 text-[11px] font-mono font-medium text-[var(--accent)] hover:bg-[var(--accent)]/20 transition-colors"
                        title="Jump to this time in audio"
                      >
                        <span className="text-[9px]">▶</span>
                        <span>{duration(c.timestamp_ms)}</span>
                      </button>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] text-[var(--text-faint)]">
                      {new Date(c.created_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleDeleteComment(c.id)}
                      disabled={deletingId === c.id}
                      className="opacity-0 group-hover:opacity-100 text-[var(--text-faint)] hover:text-[var(--bad)] p-1 transition-opacity"
                      title="Delete comment"
                    >
                      {deletingId === c.id ? (
                        <Spinner className="h-3 w-3" />
                      ) : (
                        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                          />
                        </svg>
                      )}
                    </button>
                  </div>
                </div>

                <p className="mt-2 text-[13px] leading-relaxed text-[var(--text)] whitespace-pre-wrap">
                  {c.content}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add Comment Form */}
      <div className="border-t border-[var(--border)] bg-[var(--bg-raised)] px-6 py-4">
        <form onSubmit={handleAddComment} className="max-w-2xl space-y-3">
          <div className="flex items-center gap-2 text-[12px] text-[var(--text-faint)]">
            <span>Commenting as:</span>
            <input
              type="text"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              placeholder="Name..."
              className="w-28 rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] px-2 py-1 text-[12px] text-[var(--text)] focus:border-[var(--accent)] focus:outline-none"
            />
            {currentPlayMs > 0 && (
              <label className="ml-auto flex items-center gap-1.5 cursor-pointer text-[12px] select-none text-[var(--text-dim)]">
                <input
                  type="checkbox"
                  checked={tagCurrentTime}
                  onChange={(e) => setTagCurrentTime(e.target.checked)}
                  className="accent-[var(--accent)]"
                />
                <span>
                  Attach playhead time (<span className="font-mono text-[var(--accent)]">{duration(currentPlayMs)}</span>)
                </span>
              </label>
            )}
          </div>

          <div className="flex gap-2">
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Write a comment or clinical note..."
              rows={2}
              className="flex-1 rounded-xl border border-[var(--border)] bg-[var(--bg-inset)] px-3.5 py-2.5 text-[13px] text-[var(--text)] placeholder-[var(--text-faint)] focus:border-[var(--accent)] focus:outline-none resize-none"
            />
            <Button
              type="submit"
              variant="solid"
              disabled={submitting || !content.trim()}
              className="self-end px-4 py-2"
            >
              {submitting ? <Spinner className="h-3.5 w-3.5" /> : "Post"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
