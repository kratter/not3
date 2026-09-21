import type { ReactNode } from "react";
import { cx } from "../util";

export function Button({
  children, onClick, variant = "ghost", size = "md", disabled, title, active, className, type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "ghost" | "solid" | "outline" | "danger";
  size?: "sm" | "md";
  disabled?: boolean;
  title?: string;
  active?: boolean;
  className?: string;
  type?: "button" | "submit" | "reset";
}) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors " +
    "disabled:opacity-40 disabled:pointer-events-none whitespace-nowrap";
  const sizes = { sm: "px-2 py-1 text-xs", md: "px-3 py-1.5 text-[13px]" };
  const variants = {
    ghost: "hover:bg-[var(--bg-inset)] text-[var(--text-dim)] hover:text-[var(--text)]",
    solid: "bg-[var(--accent)] text-white hover:bg-[var(--accent-dim)]",
    outline:
      "border border-[var(--border-strong)] text-[var(--text-dim)] " +
      "hover:text-[var(--text)] hover:border-[var(--text-faint)]",
    danger: "text-[var(--bad)] hover:bg-[var(--bad)]/10",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cx(
        base, sizes[size], variants[variant],
        active && "bg-[var(--accent-wash)] text-[var(--accent)]",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Chip({
  children, tone = "neutral", title,
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "good" | "warn" | "bad";
  title?: string;
}) {
  const tones = {
    neutral: "bg-[var(--bg-inset)] text-[var(--text-faint)]",
    accent: "bg-[var(--accent-wash)] text-[var(--accent)]",
    good: "bg-[var(--good)]/12 text-[var(--good)]",
    warn: "bg-[var(--warn)]/12 text-[var(--warn)]",
    bad: "bg-[var(--bad)]/12 text-[var(--bad)]",
  };
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium",
        tones[tone],
      )}
    >
      {children}
    </span>
  );
}

export function Tabs<T extends string>({
  tabs, value, onChange,
}: {
  tabs: { id: T; label: string; count?: number }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div className="flex gap-1 border-b border-[var(--border)] px-4 select-none-ui">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
          className={cx(
            "relative px-3 py-2 text-[13px] font-medium transition-colors",
            value === tab.id
              ? "text-[var(--text)]"
              : "text-[var(--text-faint)] hover:text-[var(--text-dim)]",
          )}
        >
          {tab.label}
          {tab.count !== undefined && tab.count > 0 && (
            <span className="ml-1.5 text-[11px] text-[var(--text-faint)]">{tab.count}</span>
          )}
          {value === tab.id && (
            <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-[var(--accent)]" />
          )}
        </button>
      ))}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cx("h-3.5 w-3.5 animate-spin", className)} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.2" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3"
            strokeLinecap="round" />
    </svg>
  );
}

export function Empty({
  title, hint, action,
}: {
  title: string;
  hint?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
      <p className="text-[15px] font-medium text-[var(--text-dim)]">{title}</p>
      {hint && <p className="max-w-md text-[13px] leading-relaxed text-[var(--text-faint)]">{hint}</p>}
      {action}
    </div>
  );
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1 flex-1 overflow-hidden rounded-full bg-[var(--bg-inset)]">
        <div
          className="h-full rounded-full bg-[var(--accent)] transition-[width] duration-300"
          style={{ width: `${Math.round(Math.min(1, Math.max(0, value)) * 100)}%` }}
        />
      </div>
      {label && (
        <span className="w-40 truncate text-[11px] text-[var(--text-faint)]">{label}</span>
      )}
    </div>
  );
}

/** A confidence readout that stays honest: the number, not just a colour. */
export function Confidence({ value }: { value: number }) {
  const tone = value >= 0.85 ? "good" : value >= 0.65 ? "warn" : "neutral";
  return <Chip tone={tone} title="Model confidence in this reading">{Math.round(value * 100)}%</Chip>;
}

export function Icon({ name, className }: { name: IconName; className?: string }) {
  return (
    <svg
      className={cx("h-4 w-4 shrink-0", className)}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {PATHS[name]}
    </svg>
  );
}

export type IconName =
  | "play" | "pause" | "back" | "forward" | "plus" | "pencil" | "search" | "settings"
  | "trash" | "refresh" | "sun" | "moon" | "quote" | "lens" | "export" | "alert";

const PATHS: Record<IconName, ReactNode> = {
  play: <path d="M6 4l14 8-14 8z" fill="currentColor" stroke="none" />,
  pause: <><rect x="6" y="4" width="4" height="16" rx="1" fill="currentColor" stroke="none" />
          <rect x="14" y="4" width="4" height="16" rx="1" fill="currentColor" stroke="none" /></>,
  back: <><path d="M11 4v16L3 12z" fill="currentColor" stroke="none" /><path d="M20 4v16" /></>,
  forward: <><path d="M13 4v16l8-8z" fill="currentColor" stroke="none" /><path d="M4 4v16" /></>,
  plus: <><path d="M12 5v14" /><path d="M5 12h14" /></>,
  pencil: <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>,
  settings: <><circle cx="12" cy="12" r="3" />
             <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></>,
  trash: <><path d="M3 6h18" /><path d="M8 6V4h8v2" />
          <path d="M19 6l-1 14H6L5 6" /></>,
  refresh: <><path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v6h-6" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
  moon: <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />,
  quote: <path d="M7 7h4v6a4 4 0 0 1-4 4V7zM15 7h4v6a4 4 0 0 1-4 4V7z" />,
  lens: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /></>,
  export: <><path d="M12 15V3" /><path d="m7 8 5-5 5 5" /><path d="M5 15v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" /></>,
  alert: <><circle cx="12" cy="12" r="9" /><path d="M12 8v5" /><path d="M12 16h.01" /></>,
};
