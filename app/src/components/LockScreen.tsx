import { useState } from "react";
import type { Api } from "../api";
import { Button, Spinner } from "./ui";

export function LockScreen({
  api,
  onUnlocked,
}: {
  api: Api;
  onUnlocked: () => void;
}) {
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleUnlock(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!password) {
      setError("Please enter your password");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.authVerify(password);
      if (res.ok) {
        onUnlocked();
      } else {
        setError("Incorrect password. Please try again.");
      }
    } catch (err: unknown) {
      setError(String(err instanceof Error ? err.message : err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--bg)]/95 backdrop-blur-md">
      <div className="w-full max-w-sm rounded-2xl border border-[var(--border)] bg-[var(--bg-raised)] p-7 shadow-2xl animate-in fade-in zoom-in-95 duration-200">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--accent)]/15 text-[var(--accent)] ring-1 ring-[var(--accent)]/30">
            <svg
              className="h-7 w-7"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0110 0v4" />
            </svg>
          </div>
          <h2 className="text-[17px] font-semibold text-[var(--text)]">Not3 is Locked</h2>
          <p className="mt-1 text-[13px] text-[var(--text-faint)]">
            Password protection is active. Enter your password to access your recordings, notes, and lenses.
          </p>
        </div>

        <form onSubmit={handleUnlock} className="mt-6 space-y-4">
          <div>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  setError(null);
                }}
                autoFocus
                placeholder="Enter password..."
                className={`w-full rounded-xl border bg-[var(--bg-inset)] px-3.5 py-2.5 pr-10 text-[14px] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:ring-2 ${
                  error
                    ? "border-[var(--bad)] focus:ring-[var(--bad)]/30"
                    : "border-[var(--border)] focus:border-[var(--accent)] focus:ring-[var(--accent)]/30"
                }`}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-faint)] hover:text-[var(--text)]"
                title={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? (
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18"
                    />
                  </svg>
                ) : (
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                    />
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                    />
                  </svg>
                )}
              </button>
            </div>
            {error && (
              <p className="mt-2 text-[12px] text-[var(--bad)] font-medium flex items-center gap-1">
                <span>⚠️</span> {error}
              </p>
            )}
          </div>

          <Button
            type="submit"
            variant="solid"
            disabled={loading || !password}
            className="w-full justify-center py-2.5 text-[14px] font-medium"
          >
            {loading ? <Spinner className="h-4 w-4 text-white" /> : "Unlock Not3"}
          </Button>
        </form>
      </div>
    </div>
  );
}
