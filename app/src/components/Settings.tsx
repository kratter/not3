import { useEffect, useState } from "react";
import { revealItemInDir } from "@tauri-apps/plugin-opener";

import type { Api, EngineSettings, Lens, LensRun, Status } from "../api";
import { cx } from "../util";
import { SetupModal } from "./SetupModal";
import { Button, Chip, Icon, Spinner } from "./ui";

export function Settings({
  api, lenses, onClose, onLensesChanged, theme, onToggleTheme,
}: {
  api: Api;
  lenses: Lens[];
  onClose: () => void;
  onLensesChanged: () => void;
  theme: "dark" | "light";
  onToggleTheme: () => void;
}) {
  const [status, setStatus] = useState<Status | null>(null);
  const [settings, setSettings] = useState<EngineSettings | null>(null);
  const [runs, setRuns] = useState<LensRun[]>([]);
  const [saving, setSaving] = useState(false);
  const [showSetup, setShowSetup] = useState(false);

  // App Security & Password Protection
  const [passwordRequired, setPasswordRequired] = useState(false);
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwSuccess, setPwSuccess] = useState<string | null>(null);
  const [pwSubmitting, setPwSubmitting] = useState(false);
  const [showPwForm, setShowPwForm] = useState(false);

  const loadData = () => {
    void Promise.all([api.status(), api.settings(), api.lensRuns(), api.authStatus()])
      .then(([s, cfg, r, auth]) => {
        setStatus(s);
        setSettings(cfg);
        setRuns(r);
        setPasswordRequired(auth.password_required);
      })
      .catch(() => undefined);
  };

  useEffect(() => {
    loadData();
  }, [api]);

  async function handleSetPassword(e: React.FormEvent) {
    e.preventDefault();
    setPwError(null);
    setPwSuccess(null);
    if (!newPw) {
      setPwError("Password cannot be empty");
      return;
    }
    if (newPw !== confirmPw) {
      setPwError("Passwords do not match");
      return;
    }
    setPwSubmitting(true);
    try {
      await api.setAuthPassword(newPw, passwordRequired ? currentPw : undefined);
      sessionStorage.setItem("not3_unlocked", "true");
      setPasswordRequired(true);
      setPwSuccess("Password protection enabled! Not3 will ask for this password on every restart.");
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
      setShowPwForm(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("Not Found") || msg.includes("404")) {
        setPwError("Engine service needs restart to apply authentication updates. Please restart Not3.");
      } else {
        setPwError(msg);
      }
    } finally {
      setPwSubmitting(false);
    }
  }

  async function handleRemovePassword() {
    setPwError(null);
    setPwSuccess(null);
    if (!currentPw) {
      setPwError("Please enter your current password to disable protection");
      return;
    }
    setPwSubmitting(true);
    try {
      await api.removeAuthPassword(currentPw);
      setPasswordRequired(false);
      setPwSuccess("Password protection has been removed.");
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
      setShowPwForm(false);
    } catch (err: unknown) {
      setPwError(String(err instanceof Error ? err.message : err));
    } finally {
      setPwSubmitting(false);
    }
  }

  async function update(patch: Partial<EngineSettings>) {
    setSaving(true);
    try {
      setSettings(await api.updateSettings(patch));
    } finally {
      setSaving(false);
    }
  }


  const models = status?.ollama.models ?? [];

  return (
    <div className="absolute inset-0 z-20 flex flex-col bg-[var(--bg)]">
      <header className="flex items-center gap-3 border-b border-[var(--border)] px-6 py-3">
        <h1 className="text-[15px] font-semibold">Settings</h1>
        {saving && <Spinner className="text-[var(--text-faint)]" />}
        <div className="flex-1" />
        <Button onClick={onToggleTheme} title="Toggle theme">
          <Icon name={theme === "dark" ? "sun" : "moon"} />
        </Button>
        <Button variant="outline" onClick={onClose}>
          Done
        </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        <div className="mx-auto max-w-2xl space-y-8">
          <Section title="This machine">
            {status ? (
              <div className="space-y-2 text-[13px]">
                <Row label="Transcription">
                  {status.backends.length === 0 ? (
                    <Chip tone="bad">none installed</Chip>
                  ) : (
                    <span className="flex gap-1">
                      {status.backends.map((b) => (
                        <Chip key={b.name} tone={b.name === "cpu" ? "neutral" : "good"}>
                          {b.name}
                        </Chip>
                      ))}
                    </span>
                  )}
                </Row>
                <Row label="Speech model">
                  {status.asr_model_present ? (
                    <span className="text-[var(--text-dim)]">{status.asr_model}</span>
                  ) : (
                    <Chip tone="bad">{status.asr_model} missing</Chip>
                  )}
                </Row>
                <Row label="Ollama">
                  {status.ollama.available ? (
                    <Chip tone="good">{models.length} models</Chip>
                  ) : (
                    <Chip tone="bad">not reachable at {status.ollama.url}</Chip>
                  )}
                </Row>
                <Row label="Notes folder">
                  <button
                    type="button"
                    onClick={() => void revealItemInDir(status.export_dir)}
                    className="truncate text-left text-[var(--accent)] hover:underline"
                    title={status.export_dir}
                  >
                    {status.export_dir}
                  </button>
                </Row>
                <div className="pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowSetup(true)}
                    className="text-xs"
                  >
                    <Icon name="settings" className="mr-1 h-3.5 w-3.5" />
                    Setup & Download Components
                  </Button>
                </div>
              </div>
            ) : (
              <Spinner />
            )}
          </Section>

          {settings && (
            <Section
              title="Models"
              hint="Bigger models read more carefully and run slower. Changes apply to the next run."
            >
              <div className="space-y-2">
                <Select
                  label="Summaries"
                  value={settings.model_distill}
                  options={models}
                  onChange={(v) => void update({ model_distill: v })}
                />
                <Select
                  label="Highlights"
                  value={settings.model_highlight}
                  options={models}
                  onChange={(v) => void update({ model_highlight: v })}
                />
                <Select
                  label="Patterns"
                  value={settings.model_lens}
                  options={models}
                  onChange={(v) => void update({ model_lens: v })}
                />
                <Select
                  label="Language"
                  value={settings.language}
                  options={["auto", "en", "de", "hu", "fr", "es", "it", "nl", "pt"]}
                  onChange={(v) => void update({ language: v })}
                />
              </div>
            </Section>
          )}

          <Section
            title="Lenses"
            hint="Each lens is a YAML file. Add your own and it appears here; reusing a built-in id replaces that built-in."
          >
            <div className="space-y-1.5">
              {lenses.map((lens) => (
                <label
                  key={lens.id}
                  className="flex cursor-pointer items-start gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-raised)] p-3"
                >
                  <input
                    type="checkbox"
                    checked={lens.enabled}
                    onChange={(e) => {
                      void api
                        .setLensEnabled(lens.id, e.target.checked)
                        .then(onLensesChanged);
                    }}
                    className="mt-0.5 h-3.5 w-3.5 accent-[var(--accent)]"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[13px] font-medium">{lens.name}</span>
                      <Chip>{lens.categories.length} categories</Chip>
                      {!lens.builtin && <Chip tone="accent">yours</Chip>}
                    </div>
                    <p className="mt-1 text-[12px] leading-snug text-[var(--text-faint)]">
                      {lens.description}
                    </p>
                  </div>
                </label>
              ))}
            </div>
          </Section>

          {runs.length > 0 && (
            <Section
              title="Lens accuracy"
              hint="Every observation must quote the transcript verbatim. Anything that does not is dropped before it reaches you — a high drop rate means that lens or that model is guessing."
            >
              <table className="w-full text-[12px]">
                <thead className="text-[var(--text-faint)]">
                  <tr className="border-b border-[var(--border)]">
                    <th className="py-1.5 text-left font-medium">Lens</th>
                    <th className="py-1.5 text-left font-medium">Model</th>
                    <th className="py-1.5 text-right font-medium">Proposed</th>
                    <th className="py-1.5 text-right font-medium">Kept</th>
                    <th className="py-1.5 text-right font-medium">Dropped</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => {
                    const rate = r.proposed ? r.dropped / r.proposed : 0;
                    return (
                      <tr key={`${r.lens_id}:${r.model}`} className="border-b border-[var(--border)]">
                        <td className="py-1.5 text-[var(--text-dim)]">{r.lens_id}</td>
                        <td className="py-1.5 text-[var(--text-faint)]">{r.model}</td>
                        <td className="py-1.5 text-right tabular-nums">{r.proposed}</td>
                        <td className="py-1.5 text-right tabular-nums">{r.kept}</td>
                        <td
                          className={cx(
                            "py-1.5 text-right tabular-nums",
                            rate > 0.25
                              ? "text-[var(--bad)]"
                              : rate > 0.1
                                ? "text-[var(--warn)]"
                                : "text-[var(--good)]",
                          )}
                        >
                          {r.dropped} ({Math.round(rate * 100)}%)
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Section>
          )}

          <Section
            title="App Security & Password Protection"
            hint="Require a password each time Not3 launches or restarts to protect your confidential recordings and notes."
          >
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-raised)] p-4 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span
                    className={`flex h-8 w-8 items-center justify-center rounded-xl text-[14px] ${
                      passwordRequired
                        ? "bg-[var(--good)]/15 text-[var(--good)]"
                        : "bg-[var(--text-faint)]/15 text-[var(--text-faint)]"
                    }`}
                  >
                    {passwordRequired ? "🔒" : "🔓"}
                  </span>
                  <div>
                    <h4 className="text-[13px] font-medium text-[var(--text)]">
                      {passwordRequired ? "Password Protection is ACTIVE" : "Password Protection is OFF"}
                    </h4>
                    <p className="text-[11px] text-[var(--text-faint)]">
                      {passwordRequired
                        ? "You will be prompted for your password every time the app opens or restarts."
                        : "Anyone with access to this machine can open and view notes without a password."}
                    </p>
                  </div>
                </div>

                <Button
                  size="sm"
                  variant={passwordRequired ? "outline" : "solid"}
                  onClick={() => {
                    setShowPwForm(!showPwForm);
                    setPwError(null);
                    setPwSuccess(null);
                  }}
                >
                  {showPwForm
                    ? "Cancel"
                    : passwordRequired
                      ? "Change or Remove"
                      : "Enable Password"}
                </Button>
              </div>

              {pwSuccess && (
                <p className="text-[12px] text-[var(--good)] font-medium flex items-center gap-1.5">
                  <span>✓</span> {pwSuccess}
                </p>
              )}

              {showPwForm && (
                <form onSubmit={handleSetPassword} className="border-t border-[var(--border)] pt-4 space-y-3">
                  {passwordRequired && (
                    <div>
                      <label className="block text-[11px] font-medium text-[var(--text-faint)] uppercase tracking-wider mb-1">
                        Current Password
                      </label>
                      <input
                        type="password"
                        value={currentPw}
                        onChange={(e) => setCurrentPw(e.target.value)}
                        placeholder="Enter current password..."
                        className="w-full rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] px-3 py-1.5 text-[13px] text-[var(--text)] focus:border-[var(--accent)] focus:outline-none"
                      />
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] font-medium text-[var(--text-faint)] uppercase tracking-wider mb-1">
                        {passwordRequired ? "New Password" : "Password"}
                      </label>
                      <input
                        type="password"
                        value={newPw}
                        onChange={(e) => setNewPw(e.target.value)}
                        placeholder="Create a password..."
                        className="w-full rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] px-3 py-1.5 text-[13px] text-[var(--text)] focus:border-[var(--accent)] focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-[var(--text-faint)] uppercase tracking-wider mb-1">
                        Confirm Password
                      </label>
                      <input
                        type="password"
                        value={confirmPw}
                        onChange={(e) => setConfirmPw(e.target.value)}
                        placeholder="Confirm password..."
                        className="w-full rounded-lg border border-[var(--border)] bg-[var(--bg-inset)] px-3 py-1.5 text-[13px] text-[var(--text)] focus:border-[var(--accent)] focus:outline-none"
                      />
                    </div>
                  </div>

                  {pwError && (
                    <p className="text-[12px] text-[var(--bad)] font-medium flex items-center gap-1">
                      <span>⚠️</span> {pwError}
                    </p>
                  )}

                  <div className="flex items-center justify-between pt-1">
                    {passwordRequired && (
                      <button
                        type="button"
                        onClick={handleRemovePassword}
                        disabled={pwSubmitting}
                        className="text-[12px] text-[var(--bad)] hover:underline font-medium"
                      >
                        Remove Password Protection
                      </button>
                    )}
                    <div className="flex-1" />
                    <Button
                      type="submit"
                      variant="solid"
                      size="sm"
                      disabled={pwSubmitting}
                    >
                      {pwSubmitting ? <Spinner className="h-3.5 w-3.5" /> : passwordRequired ? "Update Password" : "Save & Protect"}
                    </Button>
                  </div>
                </form>
              )}
            </div>
          </Section>

          <Section title="About">
            <p className="text-[12px] leading-relaxed text-[var(--text-faint)]">
              Everything runs on this machine — transcription through whisper.cpp,
              language work through Ollama. Nothing is uploaded. Notes are written
              as plain markdown you can open in any editor.
            </p>
            <p className="mt-2 text-[12px] leading-relaxed text-[var(--text-faint)]">
              Pattern observations describe language, tied to a quote and a
              timestamp. They are not a clinical or diagnostic assessment.
            </p>
          </Section>

          <div className="h-8" />
        </div>
      </div>

      {showSetup && (
        <SetupModal
          api={api}
          onClose={() => setShowSetup(false)}
          onComplete={() => loadData()}
        />
      )}
    </div>
  );
}

function Section({
  title, hint, children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="text-[13px] font-semibold text-[var(--text)]">{title}</h2>
      {hint && (
        <p className="mb-3 mt-1 max-w-xl text-[12px] leading-relaxed text-[var(--text-faint)]">
          {hint}
        </p>
      )}
      <div className={hint ? "" : "mt-3"}>{children}</div>
    </section>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-32 shrink-0 text-[var(--text-faint)]">{label}</span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

function Select({
  label, value, options, onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  // A model saved earlier may no longer be installed; keep showing it rather
  // than silently switching the user to something else.
  const list = options.includes(value) ? options : [value, ...options];
  return (
    <div className="flex items-center gap-3">
      <span className="w-32 shrink-0 text-[13px] text-[var(--text-faint)]">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="min-w-0 flex-1 rounded-md border border-[var(--border)] bg-[var(--bg-inset)] px-2 py-1.5 text-[13px] text-[var(--text)] focus:border-[var(--accent)] focus:outline-none"
      >
        {list.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
