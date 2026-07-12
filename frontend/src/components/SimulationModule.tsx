import { useState, useCallback, useEffect } from "react";
import { PlayIcon } from "@heroicons/react/24/solid";
import { runSimulation, listSimulationInputs, type SimulationConfig } from "../api.ts";

type RunStatus = "idle" | "running" | "success" | "error";

interface Metrics {
  totalOrders?: number;
  deliveredOrders?: number;
  slaHitRate?: number;
  totalCost?: string;
  routesWithErrors?: number;
  routesWithWarnings?: number;
}

function extractMetrics(text: string): Metrics {
  const cleanText = text.replace(/(?:\\x1b|\\u001b|\\033)\[\d+m/g, "");

  const num = (re: RegExp) => {
    const m = cleanText.match(re);
    return m ? parseFloat(m[1]) : undefined;
  };
  const raw = (re: RegExp) => {
    const m = cleanText.match(re);
    return m ? m[1] : undefined;
  };

  return {
    totalOrders: num(/total_orders:\s*(\d+)/),
    deliveredOrders: num(/delivered_orders:\s*(\d+)/),
    slaHitRate: num(/sla_hit_rate:\s*([\d.]+)%/),
    totalCost: raw(/Total delivery cost:\s*([\d.]+)/),
    routesWithErrors: num(/routes_with_errors:\s*(\d+)/),
    routesWithWarnings: num(/routes_with_warnings:\s*(\d+)/),
  };
}

function StatusBadge({ status }: { status: RunStatus }) {
  const styles: Record<RunStatus, string> = {
    idle: "bg-gray-100 text-gray-500",
    running: "bg-blue-100 text-blue-700",
    success: "bg-green-100 text-green-700",
    error: "bg-red-100 text-red-700",
  };
  const labels: Record<RunStatus, string> = {
    idle: "Idle",
    running: "Running…",
    success: "Success",
    error: "Failed",
  };
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${styles[status]}`}>
      {status === "running" && (
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-500 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-600"></span>
        </span>
      )}
      {labels[status]}
    </span>
  );
}

function MetricCard({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "good" | "bad" }) {
  const toneClasses = {
    neutral: "border-gray-200 text-gray-800",
    good: "border-green-200 text-green-700 bg-green-50",
    bad: "border-red-200 text-red-700 bg-red-50",
  }[tone];
  return (
    <div className={`rounded-lg border px-3 py-2 ${toneClasses}`}>
      <div className="text-[11px] uppercase tracking-wide text-gray-400 font-medium">{label}</div>
      <div className="text-lg font-semibold leading-tight">{value}</div>
    </div>
  );
}

export default function SimulationModule() {
  const [output, setOutput] = useState("");
  const [status, setStatus] = useState<RunStatus>("idle");
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [errorMessage, setErrorMessage] = useState("");

  const [inputs, setInputs] = useState<string[]>(["test_data_innopolis.json"]);
  const [config, setConfig] = useState<Required<SimulationConfig>>({
    input: "test_data_innopolis.json",
    time_step: 5,
    max_steps: 100,
    strict: false,
  });

  useEffect(() => {
    listSimulationInputs().then((files) => {
      setInputs(files);
      if (files.length && !files.includes(config.input)) {
        setConfig((c) => ({ ...c, input: files[0] }));
      }
    });
  }, []);

  const loading = status === "running";

  const handleRun = useCallback(async () => {
    setStatus("running");
    setOutput("");
    setMetrics(null);
    setErrorMessage("");
    const startedAt = performance.now();
    try {
      let text = await runSimulation(config);
      text = text.replace(/\\n/g, "\n");
      setOutput(text);
      setMetrics(extractMetrics(text));
      setStatus("success");
    } catch (error) {
      console.error("Simulation failed:", error);
      setErrorMessage(String(error instanceof Error ? error.message : error));
      setStatus("error");
    } finally {
      setElapsedMs(performance.now() - startedAt);
    }
  }, [config]);

  const formatOutput = (text: string) => {
    const lines = text.split("\n");
    let html = "";

    for (const line of lines) {
      if (line.trim() === "") {
        html += '<div style="height:0.5rem;"></div>';
        continue;
      }

      let content = line;
      let prefix = "";

      const tsMatch = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*(.*)/);
      if (tsMatch) {
        prefix = `<span style="color:#9ca3af;margin-right:0.5rem;">${tsMatch[1]}</span>`;
        content = tsMatch[2];
      }

      let activeStyles = 0;
      let contentHtml = "";

      const parts = content.split(/(?:\\x1b|\\u001b|\\033)\[(\d+)m/);

      for (let i = 0; i < parts.length; i++) {
        if (i % 2 === 0) {
          contentHtml += parts[i].replace(/</g, "&lt;").replace(/>/g, "&gt;");
        } else {
          const code = parts[i];
          if (code === "0") {
            contentHtml += "</span>".repeat(activeStyles);
            activeStyles = 0;
          } else {
            let style = "";
            switch (code) {
              case "94": style = "color: #3b82f6;"; break;
              case "92": style = "color: #16a34a;"; break;
              case "93": style = "color: #eab308;"; break;
              case "91": style = "color: #ef4444;"; break;
              case "1":  style = "font-weight: 700;"; break;
              case "2":  style = "color: #9ca3af;"; break;
            }

            if (style) {
              contentHtml += `<span style="${style}">`;
              activeStyles++;
            }
          }
        }
      }

      contentHtml += "</span>".repeat(activeStyles);

      contentHtml = contentHtml.replace(/\[DEBUG\]/g, '<span style="color:#9ca3af;font-weight:600;">[DEBUG]</span>');
      contentHtml = contentHtml.replace(/\[INFO\]/g, '<span style="color:#16a34a;font-weight:600;">[INFO]</span>');
      contentHtml = contentHtml.replace(/\[WARNING\]/g, '<span style="color:#ca8a04;font-weight:600;">[WARNING]</span>');
      contentHtml = contentHtml.replace(/\[ERROR\]/g, '<span style="color:#dc2626;font-weight:600;">[ERROR]</span>');
      contentHtml = contentHtml.replace(/\[CRITICAL\]/g, '<span style="color:#dc2626;font-weight:700;">[CRITICAL]</span>');

      html += `<div style="font-family:monospace;font-size:0.875rem;white-space:pre-wrap;">${prefix}${contentHtml}</div>`;
    }

    return html;
  };

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-gray-800">Simulation module</h2>
          <StatusBadge status={status} />
        </div>
        <button
          onClick={handleRun}
          disabled={loading}
          className={`inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium shadow-sm
            ${
              loading
                ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                : "bg-blue-600 text-white hover:bg-blue-700"
            }
          `}
        >
          {loading ? (
            <svg className="animate-spin h-4 w-4 mr-2" viewBox="0 0 24 24">
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
                fill="none"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
              />
            </svg>
          ) : (
            <PlayIcon className="h-4 w-4 mr-1.5" />
          )}
          Run
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <label className="flex flex-col gap-1 text-xs font-medium text-gray-500 col-span-2 sm:col-span-1">
          Dataset
          <select
            value={config.input}
            disabled={loading}
            onChange={(e) => setConfig((c) => ({ ...c, input: e.target.value }))}
            className="border border-gray-200 rounded-md px-2 py-1.5 text-sm text-gray-800 bg-white disabled:bg-gray-50"
          >
            {inputs.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs font-medium text-gray-500">
          Time step (min)
          <input
            type="number"
            min={1}
            value={config.time_step}
            disabled={loading}
            onChange={(e) => setConfig((c) => ({ ...c, time_step: Number(e.target.value) || 1 }))}
            className="border border-gray-200 rounded-md px-2 py-1.5 text-sm text-gray-800 disabled:bg-gray-50"
          />
        </label>

        <label className="flex flex-col gap-1 text-xs font-medium text-gray-500">
          Max steps
          <input
            type="number"
            min={1}
            value={config.max_steps}
            disabled={loading}
            onChange={(e) => setConfig((c) => ({ ...c, max_steps: Number(e.target.value) || 1 }))}
            className="border border-gray-200 rounded-md px-2 py-1.5 text-sm text-gray-800 disabled:bg-gray-50"
          />
        </label>

        <label className="flex items-center gap-2 text-xs font-medium text-gray-500 self-end pb-1.5">
          <input
            type="checkbox"
            checked={config.strict}
            disabled={loading}
            onChange={(e) => setConfig((c) => ({ ...c, strict: e.target.checked }))}
            className="rounded border-gray-300"
          />
          Strict validation
        </label>
      </div>

      {status === "success" && metrics && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mb-4">
          <MetricCard label="Delivered" value={`${metrics.deliveredOrders ?? "–"}/${metrics.totalOrders ?? "–"}`} />
          <MetricCard
            label="SLA hit rate"
            value={metrics.slaHitRate !== undefined ? `${metrics.slaHitRate.toFixed(0)}%` : "–"}
            tone={metrics.slaHitRate !== undefined ? (metrics.slaHitRate >= 95 ? "good" : "bad") : "neutral"}
          />
          <MetricCard label="Total cost" value={metrics.totalCost !== undefined ? `${metrics.totalCost} ₽` : "–"} />
          <MetricCard
            label="Route errors"
            value={`${metrics.routesWithErrors ?? 0}`}
            tone={metrics.routesWithErrors ? "bad" : "good"}
          />
          <MetricCard
            label="Route warnings"
            value={`${metrics.routesWithWarnings ?? 0}`}
            tone={metrics.routesWithWarnings ? "bad" : "good"}
          />
        </div>
      )}

      {status === "error" && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 text-red-700 text-sm px-3 py-2">
          {errorMessage || "Simulation failed."}
        </div>
      )}

      {elapsedMs !== null && status !== "running" && (
        <div className="text-xs text-gray-400 mb-2">
          {status === "success" ? "Completed" : "Stopped"} in {(elapsedMs / 1000).toFixed(1)}s
        </div>
      )}

      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 max-h-96 overflow-auto min-h-[120px]">
        {output ? (
          <div dangerouslySetInnerHTML={{ __html: formatOutput(output) }} />
        ) : (
          <p className="text-sm text-gray-400 italic m-0">
            Press Run to start simulation.
          </p>
        )}
      </div>
    </div>
  );
}