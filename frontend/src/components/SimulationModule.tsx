import { useState, useCallback } from "react";
import { PlayIcon } from "@heroicons/react/24/solid";
import { runSimulation } from "../mockData";

export default function SimulationModule() {
  const [output, setOutput] = useState("");
  const [loading, setLoading] = useState(false);

  const handleRun = useCallback(async () => {
    setLoading(true);
    const text = await runSimulation();
    setOutput(text);
    setLoading(false);
  }, []);

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">Simulation module</h2>
        <button
          onClick={handleRun}
          disabled={loading}
          className={`inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium shadow-sm
            ${loading
              ? "bg-gray-300 text-gray-500 cursor-not-allowed"
              : "bg-blue-600 text-white hover:bg-blue-700"}
          `}
        >
          {loading ? (
            <svg className="animate-spin h-4 w-4 mr-2" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
          ) : (
            <PlayIcon className="h-4 w-4 mr-1.5" />
          )}
          Run
        </button>
      </div>

      {output ? (
        <pre className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-sm font-mono text-gray-800 whitespace-pre-wrap max-h-96 overflow-auto">
          {output}
        </pre>
      ) : (
        <p className="text-sm text-gray-400 italic">Press Run to start simulation.</p>
      )}
    </div>
  );
}