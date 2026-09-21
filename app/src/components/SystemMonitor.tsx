import { useEffect, useRef, useState } from "react";
import type { Api, SystemMetrics } from "../api";
import { cx } from "../util";
import { Icon } from "./ui";

interface SystemMonitorProps {
  api: Api;
  variant?: "sidebar" | "floating";
  defaultDock?: "right" | "left";
}

interface MetricPoint {
  time: number;
  cpu: number;
  gpu: number;
  ai: number;
}

const MAX_POINTS = 24;

/** Render a smooth SVG sparkline with gradient fill */
function Sparkline({
  data,
  color,
  gradientId,
  height = 36,
  width = 180,
  maxVal = 100,
}: {
  data: number[];
  color: string;
  gradientId: string;
  height?: number;
  width?: number;
  maxVal?: number;
}) {
  if (data.length < 2) {
    return (
      <svg width={width} height={height} className="overflow-visible">
        <line x1={0} y1={height} x2={width} y2={height} stroke="var(--border)" strokeWidth={1} />
      </svg>
    );
  }

  const stepX = width / (MAX_POINTS - 1);
  const startOffset = (MAX_POINTS - data.length) * stepX;

  const points = data.map((val, idx) => {
    const x = startOffset + idx * stepX;
    const clamped = Math.max(0, Math.min(maxVal, val));
    const y = height - (clamped / maxVal) * (height - 4) - 2;
    return { x, y };
  });

  if (points.length < 2) {
    return (
      <svg width={width} height={height} className="overflow-visible">
        <line x1={0} y1={height} x2={width} y2={height} stroke="var(--border)" strokeWidth={1} />
      </svg>
    );
  }

  const firstPt = points[0];
  const lastPt = points[points.length - 1];
  if (!firstPt || !lastPt) return null;

  const pathD = points.reduce(
    (acc, pt, i) => (i === 0 ? `M ${pt.x} ${pt.y}` : `${acc} L ${pt.x} ${pt.y}`),
    "",
  );

  const areaD = `${pathD} L ${lastPt.x} ${height} L ${firstPt.x} ${height} Z`;

  return (
    <svg width={width} height={height} className="overflow-visible">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0.0" />
        </linearGradient>
      </defs>
      <path d={areaD} fill={`url(#${gradientId})`} />
      <path d={pathD} fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <circle
        cx={lastPt.x}
        cy={lastPt.y}
        r="2.5"
        fill={color}
      />
    </svg>
  );
}

export function SystemMonitor({
  api,
  variant = "sidebar",
  defaultDock = "right",
}: SystemMonitorProps) {
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [history, setHistory] = useState<MetricPoint[]>([]);
  const [expanded, setExpanded] = useState(() => {
    if (variant === "sidebar") {
      return localStorage.getItem("not3_sidebar_perf_expanded") === "true";
    }
    return false;
  });
  const [dock, setDock] = useState<"right" | "left">(() => {
    return (localStorage.getItem("not3_monitor_dock") as "right" | "left") || defaultDock;
  });


  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let active = true;

    async function fetchStats() {
      try {
        const data = await api.systemMetrics();
        if (!active) return;
        setMetrics(data);

        setHistory((prev) => {
          const pt: MetricPoint = {
            time: data.timestamp,
            cpu: data.cpu.percent,
            gpu: data.gpu.available ? data.gpu.utilization : 0,
            ai: data.ai.load_percent,
          };
          const next = [...prev, pt];
          return next.slice(-MAX_POINTS);
        });
      } catch {
        /* ignore polling errors */
      }
    }

    void fetchStats();
    timerRef.current = window.setInterval(fetchStats, 1600);

    return () => {
      active = false;
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [api]);

  function handleSetDock(newDock: "right" | "left") {
    setDock(newDock);
    localStorage.setItem("not3_monitor_dock", newDock);
  }

  const cpuVals = history.map((h) => h.cpu);
  const gpuVals = history.map((h) => h.gpu);
  const aiVals = history.map((h) => h.ai);

  const currentCpu = metrics?.cpu.percent ?? 0;
  const currentGpu = metrics?.gpu.available ? metrics.gpu.utilization : 0;
  const currentAi = metrics?.ai.load_percent ?? 0;
  const isAiBusy = metrics?.ai.busy ?? false;

  if (variant === "sidebar") {
    return (
      <div className="border-t border-[var(--border)] bg-[var(--bg-raised)] select-none-ui transition-all">
        {/* Clickable Header bar */}
        <button
          type="button"
          onClick={() => {
            const next = !expanded;
            setExpanded(next);
            localStorage.setItem("not3_sidebar_perf_expanded", String(next));
          }}
          className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-[var(--bg-inset)]/50 transition-colors"
          title="Toggle hardware & AI performance meters"
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <span
              className={cx(
                "h-2 w-2 shrink-0 rounded-full",
                isAiBusy
                  ? "bg-[var(--accent)] animate-pulse shadow-sm shadow-[var(--accent)]"
                  : currentGpu > 20
                    ? "bg-emerald-400"
                    : "bg-emerald-500/70",
              )}
            />
            <span className="text-[11px] font-semibold text-[var(--text-dim)] truncate">Performance</span>
          </div>

          <div className="flex items-center gap-1.5 text-[11px] shrink-0">
            <span className="font-semibold text-emerald-400 font-mono text-[10px]">
              {currentGpu}%
            </span>
            <span className="text-[var(--border-strong)]">•</span>
            <span className="font-semibold text-sky-400 font-mono text-[10px]">
              {Math.round(currentCpu)}%
            </span>
            <span className="text-[var(--border-strong)]">•</span>
            <span
              className={cx(
                "font-semibold font-mono text-[9px] px-1 py-0.2 rounded",
                isAiBusy ? "bg-[var(--accent)]/20 text-[var(--accent)]" : "text-[var(--text-faint)]",
              )}
            >
              {isAiBusy ? "AI" : "IDLE"}
            </span>
            <span className="text-[9px] text-[var(--text-faint)] ml-0.5">
              {expanded ? "▼" : "▲"}
            </span>
          </div>
        </button>

        {/* Expanded detailed sparklines inside sidebar */}
        {expanded && (
          <div className="px-3 pb-3 pt-1 space-y-3 border-t border-[var(--border)]/40 bg-[var(--bg-inset)]/20 animate-in fade-in duration-150">
            {/* 1. GPU */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-semibold text-emerald-400 flex items-center gap-1">
                  <span>GPU</span>
                  <span className="text-[10px] text-[var(--text-faint)] font-normal truncate max-w-32">
                    {metrics?.gpu.available ? metrics.gpu.name.replace("NVIDIA GeForce ", "") : "None"}
                  </span>
                </span>
                <span className="font-mono text-[11px] tabular-nums font-semibold">
                  {currentGpu}%
                  {metrics?.gpu.available && metrics.gpu.temperature > 0 && (
                    <span className="ml-1 text-[10px] text-[var(--text-faint)] font-normal">
                      {metrics.gpu.temperature}°C
                    </span>
                  )}
                </span>
              </div>
              <div className="rounded-lg bg-[var(--bg-inset)]/70 px-1.5 py-1 flex justify-center">
                <Sparkline
                  data={gpuVals}
                  color="#34d399"
                  gradientId="sb-gpu-grad"
                  height={26}
                  width={245}
                />
              </div>
              {metrics?.gpu.available && (
                <div className="flex justify-between text-[10px] text-[var(--text-faint)] px-0.5">
                  <span>VRAM: {metrics.gpu.memory_used_mb} / {metrics.gpu.memory_total_mb} MB</span>
                  <span>{metrics.gpu.memory_percent}%</span>
                </div>
              )}
            </div>

            {/* 2. CPU */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-semibold text-sky-400 flex items-center gap-1">
                  <span>CPU</span>
                  <span className="text-[10px] text-[var(--text-faint)] font-normal">
                    {metrics?.cpu.cores ? `${metrics.cpu.cores} cores` : ""}
                  </span>
                </span>
                <span className="font-mono text-[11px] tabular-nums font-semibold">
                  {Math.round(currentCpu)}%
                </span>
              </div>
              <div className="rounded-lg bg-[var(--bg-inset)]/70 px-1.5 py-1 flex justify-center">
                <Sparkline
                  data={cpuVals}
                  color="#38bdf8"
                  gradientId="sb-cpu-grad"
                  height={26}
                  width={245}
                />
              </div>
              {metrics?.memory && (
                <div className="flex justify-between text-[10px] text-[var(--text-faint)] px-0.5">
                  <span>RAM: {metrics.memory.used_gb} / {metrics.memory.total_gb} GB</span>
                  <span>{Math.round(metrics.memory.percent)}%</span>
                </div>
              )}
            </div>

            {/* 3. AI Pipeline */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-semibold text-[var(--accent)] flex items-center gap-1">
                  <span>AI Pipeline</span>
                  <span
                    className={cx(
                      "text-[9px] rounded px-1 py-0.2 font-medium",
                      isAiBusy
                        ? "bg-[var(--accent)]/20 text-[var(--accent)]"
                        : "bg-[var(--bg-inset)] text-[var(--text-faint)]",
                    )}
                  >
                    {isAiBusy ? (metrics?.ai.stage ? metrics.ai.stage.toUpperCase() : "ACTIVE") : "IDLE"}
                  </span>
                </span>
                <span className="font-mono text-[11px] tabular-nums font-semibold text-[var(--accent)]">
                  {currentAi}%
                </span>
              </div>
              <div className="rounded-lg bg-[var(--bg-inset)]/70 px-1.5 py-1 flex justify-center">
                <Sparkline
                  data={aiVals}
                  color="#818cf8"
                  gradientId="sb-ai-grad"
                  height={26}
                  width={245}
                />
              </div>
              <div className="flex justify-between text-[10px] text-[var(--text-faint)] px-0.5">
                <span className="truncate max-w-32">ASR: {metrics?.ai.asr_model ?? "whisper"}</span>
                <span className="truncate max-w-24">LLM: {metrics?.ai.llm_model ?? "ollama"}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <aside
      aria-label="System Hardware & AI Monitor"
      className={cx(
        "fixed z-40 select-none-ui transition-all duration-200",
        dock === "right"
          ? "bottom-18 right-4"
          : "bottom-18 left-4",
      )}
    >

      {/* EXPANDED HUD CARD */}
      {expanded ? (
        <div className="w-80 rounded-2xl border border-[var(--border)] bg-[var(--bg-raised)]/95 p-4 shadow-2xl backdrop-blur-md animate-in fade-in zoom-in-95 duration-150 text-[var(--text)]">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-[var(--border)] pb-2.5 mb-3">
            <div className="flex items-center gap-2">
              <span
                className={cx(
                  "h-2 w-2 rounded-full",
                  isAiBusy ? "bg-[var(--accent)] animate-pulse" : "bg-emerald-500",
                )}
              />
              <span className="text-[12px] font-semibold tracking-tight">System & AI Monitor</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => handleSetDock(dock === "right" ? "left" : "right")}
                title={`Dock to ${dock === "right" ? "left" : "right"}`}
                className="rounded p-1 text-[var(--text-faint)] hover:text-[var(--text)] hover:bg-[var(--bg-inset)] text-[10px]"
              >
                {dock === "right" ? "◧ Left" : "Right ◨"}
              </button>
              <button
                type="button"
                onClick={() => setExpanded(false)}
                className="rounded p-1 text-[var(--text-faint)] hover:text-[var(--text)] hover:bg-[var(--bg-inset)]"
                title="Collapse monitor"
              >
                <Icon name="x" className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {/* 1. GPU STATS & PLOT */}
          <div className="space-y-1 mb-3.5">
            <div className="flex items-center justify-between text-[11px]">
              <span className="font-semibold text-emerald-400 flex items-center gap-1">
                <span>GPU</span>
                <span className="text-[10px] text-[var(--text-faint)] font-normal truncate max-w-36">
                  {metrics?.gpu.available ? metrics.gpu.name.replace("NVIDIA GeForce ", "") : "None"}
                </span>
              </span>
              <span className="font-mono text-[11px] tabular-nums font-semibold">
                {currentGpu}%
                {metrics?.gpu.available && metrics.gpu.temperature > 0 && (
                  <span className="ml-1 text-[10px] text-[var(--text-faint)] font-normal">
                    {metrics.gpu.temperature}°C
                  </span>
                )}
              </span>
            </div>
            <div className="rounded-lg bg-[var(--bg-inset)]/60 px-2 py-1.5 flex justify-center">
              <Sparkline
                data={gpuVals}
                color="#34d399"
                gradientId="gpu-grad"
                height={32}
                width={268}
              />
            </div>
            {metrics?.gpu.available && (
              <div className="flex justify-between text-[10px] text-[var(--text-faint)] px-0.5">
                <span>VRAM: {metrics.gpu.memory_used_mb} / {metrics.gpu.memory_total_mb} MB</span>
                <span>{metrics.gpu.memory_percent}%</span>
              </div>
            )}
          </div>

          {/* 2. CPU STATS & PLOT */}
          <div className="space-y-1 mb-3.5">
            <div className="flex items-center justify-between text-[11px]">
              <span className="font-semibold text-sky-400 flex items-center gap-1">
                <span>CPU</span>
                <span className="text-[10px] text-[var(--text-faint)] font-normal">
                  {metrics?.cpu.cores ? `${metrics.cpu.cores} cores` : ""}
                </span>
              </span>
              <span className="font-mono text-[11px] tabular-nums font-semibold">
                {Math.round(currentCpu)}%
              </span>
            </div>
            <div className="rounded-lg bg-[var(--bg-inset)]/60 px-2 py-1.5 flex justify-center">
              <Sparkline
                data={cpuVals}
                color="#38bdf8"
                gradientId="cpu-grad"
                height={32}
                width={268}
              />
            </div>
            {metrics?.memory && (
              <div className="flex justify-between text-[10px] text-[var(--text-faint)] px-0.5">
                <span>RAM: {metrics.memory.used_gb} / {metrics.memory.total_gb} GB</span>
                <span>{Math.round(metrics.memory.percent)}%</span>
              </div>
            )}
          </div>

          {/* 3. AI ENGINE LOAD & PLOT */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[11px]">
              <span className="font-semibold text-[var(--accent)] flex items-center gap-1">
                <span>AI Pipeline</span>
                <span
                  className={cx(
                    "text-[10px] rounded px-1 py-0.2 font-medium",
                    isAiBusy
                      ? "bg-[var(--accent)]/20 text-[var(--accent)]"
                      : "bg-[var(--bg-inset)] text-[var(--text-faint)]",
                  )}
                >
                  {isAiBusy ? (metrics?.ai.stage ? metrics.ai.stage.toUpperCase() : "ACTIVE") : "IDLE"}
                </span>
              </span>
              <span className="font-mono text-[11px] tabular-nums font-semibold text-[var(--accent)]">
                {currentAi}%
              </span>
            </div>
            <div className="rounded-lg bg-[var(--bg-inset)]/60 px-2 py-1.5 flex justify-center">
              <Sparkline
                data={aiVals}
                color="#818cf8"
                gradientId="ai-grad"
                height={32}
                width={268}
              />
            </div>
            <div className="flex justify-between text-[10px] text-[var(--text-faint)] px-0.5">
              <span className="truncate max-w-44">ASR: {metrics?.ai.asr_model ?? "whisper"}</span>
              <span className="truncate max-w-24">LLM: {metrics?.ai.llm_model ?? "ollama"}</span>
            </div>
          </div>
        </div>
      ) : (
        /* COMPACT FLOATING STATUS PILL */
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="group flex items-center gap-2.5 rounded-full border border-[var(--border)] bg-[var(--bg-raised)]/90 px-3 py-1.5 shadow-lg backdrop-blur-md hover:border-[var(--accent)]/60 hover:bg-[var(--bg-raised)] transition-all"
          title="Click to expand real-time GPU, CPU & AI plots"
        >
          {/* Status Dot */}
          <span
            className={cx(
              "h-2 w-2 rounded-full transition-colors",
              isAiBusy
                ? "bg-[var(--accent)] animate-pulse shadow-sm shadow-[var(--accent)]"
                : currentGpu > 20
                  ? "bg-emerald-400"
                  : "bg-emerald-500/70",
            )}
          />

          {/* GPU Stat & Mini Sparkline */}
          <div className="flex items-center gap-1.5 text-[11px]">
            <span className="font-semibold text-emerald-400">GPU</span>
            <span className="font-mono tabular-nums text-[11px] text-[var(--text)] font-medium">
              {currentGpu}%
            </span>
            <div className="opacity-70 group-hover:opacity-100 transition-opacity">
              <Sparkline data={gpuVals.slice(-8)} color="#34d399" gradientId="pill-gpu" height={14} width={32} />
            </div>
          </div>

          <span className="text-[var(--border-strong)]">|</span>

          {/* CPU Stat & Mini Sparkline */}
          <div className="flex items-center gap-1.5 text-[11px]">
            <span className="font-semibold text-sky-400">CPU</span>
            <span className="font-mono tabular-nums text-[11px] text-[var(--text)] font-medium">
              {Math.round(currentCpu)}%
            </span>
            <div className="opacity-70 group-hover:opacity-100 transition-opacity">
              <Sparkline data={cpuVals.slice(-8)} color="#38bdf8" gradientId="pill-cpu" height={14} width={32} />
            </div>
          </div>

          <span className="text-[var(--border-strong)]">|</span>

          {/* AI Stat & Mini Sparkline */}
          <div className="flex items-center gap-1.5 text-[11px]">
            <span className="font-semibold text-[var(--accent)]">AI</span>
            <span
              className={cx(
                "font-mono tabular-nums text-[11px] font-medium",
                isAiBusy ? "text-[var(--accent)]" : "text-[var(--text-faint)]",
              )}
            >
              {isAiBusy ? "BUSY" : "IDLE"}
            </span>
            <div className="opacity-70 group-hover:opacity-100 transition-opacity">
              <Sparkline data={aiVals.slice(-8)} color="#818cf8" gradientId="pill-ai" height={14} width={32} />
            </div>
          </div>

          {/* Expand Chevron Indicator */}
          <span className="text-[10px] text-[var(--text-faint)] group-hover:text-[var(--accent)] group-hover:translate-y-[-1px] transition-all ml-0.5">
            ▲
          </span>
        </button>
      )}
    </aside>
  );
}
