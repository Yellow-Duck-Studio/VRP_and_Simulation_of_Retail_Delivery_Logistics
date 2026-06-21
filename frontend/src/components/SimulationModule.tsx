import { useState, useCallback } from "react";
import { PlayIcon } from "@heroicons/react/24/solid";
import { runSimulation } from "../api.ts";

export default function SimulationModule() {
  const [output, setOutput] = useState("");
  const [loading, setLoading] = useState(false);

  const handleRun = useCallback(async () => {
    setLoading(true);
    setOutput("");
    try {
      let text = await runSimulation();
      text = text.replace(/\\n/g, "\n");
      setOutput(text);
    } catch (error) {
      console.error("Simulation failed:", error);
      setOutput(`Simulation failed:\n${error}`);
    } finally {
      setLoading(false);
    }
  }, []);

  const formatOutput = (text: string) => {
    const lines = text.split("\n");
    let html = "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed === "") {
        html += '<div style="height:0.5rem;"></div>';
      } else if (/^===.*===/.test(trimmed)) {
        html += `<div style="font-weight:bold;color:#1e40af;font-size:1rem;margin-top:0.5rem;">${line}</div>`;
      } else {
        const colonIndex = line.indexOf(":");
        if (colonIndex !== -1 && /^\s+/.test(line)) {
          const leadingSpaces = line.match(/^(\s+)/)?.[1] || "";
          const indentLevel = leadingSpaces.length;
          const key = line.substring(0, colonIndex).trim();
          const value = line.substring(colonIndex + 1).trim();
          const pad = (indentLevel / 2) + "rem";
          html += `<div style="padding-left:${pad};font-family:monospace;font-size:0.875rem;"><span style="font-weight:600;color:#374151;">${key}:</span> ${value}</div>`;
        } else {
          html += `<div style="font-family:monospace;font-size:0.875rem;white-space:pre-wrap;">${line}</div>`;
        }
      }
    }
    return html;
  };

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">Simulation module</h2>
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