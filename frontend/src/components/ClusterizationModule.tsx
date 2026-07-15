import { useState, useCallback, useRef, useEffect } from "react";
import { PlayIcon } from "@heroicons/react/24/solid";
import {
  runClusteringWithProgress,
  getTasksFromAlgoData,
  getVariantsFromAlgoData,
  loadGnnAlgorithmResult,
  type ClusterProgressEvent,
  type AllResults,
  type AlgorithmResults,
  type GnnTaskResult,
} from "../api.ts";
import ClusterMapCanvas from "./ClusterMapCanvas";

const AVAILABLE_EVO_ALGORITHMS = ["DBScan", "Clarke Wright", "Sweep", "Destroy & Repair", "Random"];
const AVAILABLE_STANDALONE_ALGORITHMS = ["GNN"];
const GNN_ALGO = "GNN";
const GNN_ALGORITHMS = ["greedy", "clarke_wright", "sweep", "dbscan_eps_0.1", "dbscan_eps_0.2", "dbscan_eps_0.4", "dbscan_eps_0.5", "dbscan_eps_0.6", "dbscan_eps_0.8", "dbscan_eps_0.9"];

type PolygonVariantIdx = { polygonIdx: number; variantIdx: number };
const initialSlot: PolygonVariantIdx = { polygonIdx: 0, variantIdx: 0 };

function RunLogPanel({ lines, active }: { lines: string[]; active: boolean }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines]);

  return (
    <div className="mt-3 rounded-lg overflow-hidden border border-gray-200">
      <div className="px-3 py-1.5 flex items-center gap-2 border-b border-gray-200">
        <span className={`h-2 w-2 rounded-full ${active ? "bg-green-400" : "bg-gray-500"}`} />
        <span className="text-xs text-gray-400 font-mono">
          {active ? "running..." : "in queue"}
        </span>
      </div>
      <div ref={scrollRef} className="text-[11px] font-mono leading-relaxed p-3 h-40 overflow-y-auto">
        {lines.length === 0 ? (
          <div className="text-gray-500">Wait for output...</div>
        ) : (
          lines.map((line, i) => {
            const isHeader = line.includes("RUNNING EVOLUTION") || line.startsWith("===");
            const isSuccess = line.startsWith("Successfully") || line.startsWith("Done!");
            const isGen = line.startsWith("Gen ");
            const cls = isHeader
              ? "text-amber-500 font-semibold"
              : isSuccess
              ? "text-emerald-500"
              : isGen
              ? "text-sky-500"
              : "text-gray-500";
            return (
              <div key={i} className={cls}>
                {line}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function AlgoStatusBadge({ isActive, hasData }: { isActive: boolean; hasData: boolean }) {
  if (isActive) {
    return (
      <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
        Running
      </span>
    );
  }
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${hasData ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-500"}`}>
      {hasData ? "Done" : "In queue"}
    </span>
  );
}

// One polygon/variant-navigable map. Used both standalone (evolutionary
// algorithms) and as one half of the GNN side-by-side view.
function MapSlot({
  slotLabel,
  algoData,
  isRunning,
  dataset,
  state,
  onPolygonChange,
  onVariantChange,
  costLabel,
}: {
  slotLabel?: string;
  algoData: AlgorithmResults | undefined;
  isRunning: boolean;
  dataset: string;
  state: PolygonVariantIdx;
  onPolygonChange: (value: number) => void;
  onVariantChange: (value: number) => void;
  costLabel?: string;
}) {
  const tasks = algoData ? getTasksFromAlgoData(algoData) : [];
  const taskKey = tasks[state.polygonIdx] ?? tasks[0];
  const variants = algoData && taskKey ? getVariantsFromAlgoData(algoData, taskKey) : [];
  const variant = variants[state.variantIdx];
  const clusters = variant ? variant.clusters : [];

  if (tasks.length === 0) {
    return <ClusterMapCanvas clusters={[]} taskId="" dataset={dataset} isRunning={isRunning} />;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <div className="flex items-center gap-4">
          {slotLabel && (
            <span className="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-0.5 rounded">{slotLabel}</span>
          )}
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-gray-500">Polygon</span>
            <input
              type="number"
              min={1}
              max={Math.max(tasks.length, 1)}
              value={state.polygonIdx + 1}
              onChange={(e) => onPolygonChange(parseInt(e.target.value, 10) || 1)}
              className="w-16 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm px-2 py-1"
            />
            <span className="text-xs text-gray-400">/ {tasks.length}</span>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-xs text-gray-500">Variant</span>
            <input
              type="number"
              min={1}
              max={Math.max(variants.length, 1)}
              value={state.variantIdx + 1}
              onChange={(e) => onVariantChange(parseInt(e.target.value, 10) || 1)}
              className="w-16 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm px-2 py-1"
            />
            <span className="text-xs text-gray-400">/ {variants.length}</span>
          </div>
        </div>

        {variant?.fitness_score !== undefined && (
          <span className="text-xs px-2 py-0.5 rounded font-medium bg-emerald-100 text-emerald-700">
            {costLabel ?? "Score"}: {variant.fitness_score.toFixed(2)}
          </span>
        )}
      </div>

      <ClusterMapCanvas clusters={clusters} taskId={taskKey} dataset={dataset} />
    </div>
  );
}

export default function ClusterizationModule() {
  const [selectedAlgo, setSelectedAlgo] = useState<string[]>([]);
  const [results, setResults] = useState<AllResults>({});
  const [loading, setLoading] = useState(false);
  const [activeAlgo, setActiveAlgo] = useState<string | null>(null);
  const [logsByAlgo, setLogsByAlgo] = useState<Record<string, string[]>>({});
  const [dataset, setDataset] = useState<"small" | "large" | "big">("small");

  // Polygon/variant navigation state for single-map (evolutionary) panels.
  const [polygonIdx, setPolygonIdx] = useState<Record<string, number>>({});
  const [variantIdx, setVariantIdx] = useState<Record<string, number>>({});

  // Independent navigation state for the two halves of the GNN dual-map panel.
  const [gnnSlotA, setGnnSlotA] = useState<PolygonVariantIdx>(initialSlot);
  const [gnnSlotB, setGnnSlotB] = useState<PolygonVariantIdx>(initialSlot);
  const [gnnAlgoA, setGnnAlgoA] = useState<string>("clarke_wright");
  const [gnnAlgoB, setGnnAlgoB] = useState<string>("sweep");
  const [gnnDataA, setGnnDataA] = useState<GnnTaskResult[] | null>(null);
  const [gnnDataB, setGnnDataB] = useState<GnnTaskResult[] | null>(null);

  useEffect(() => {
    if (selectedAlgo.includes(GNN_ALGO) && gnnAlgoA) {
      loadGnnAlgorithmResult(gnnAlgoA)
        .then(setGnnDataA)
        .catch((err) => console.error("Failed to load GNN data A:", err));
    }
  }, [gnnAlgoA, selectedAlgo]);

  useEffect(() => {
    if (selectedAlgo.includes(GNN_ALGO) && gnnAlgoB) {
      loadGnnAlgorithmResult(gnnAlgoB)
        .then(setGnnDataB)
        .catch((err) => console.error("Failed to load GNN data B:", err));
    }
  }, [gnnAlgoB, selectedAlgo]);

  const toggleAlgorithm = (alg: string) => {
    setSelectedAlgo((prev) =>
      prev.includes(alg) ? prev.filter((a) => a !== alg) : [...prev, alg]
    );
  };

  const handleRun = useCallback(async () => {
    if (selectedAlgo.length === 0) return;
    setLoading(true);
    setResults({});
    setPolygonIdx({});
    setVariantIdx({});
    setGnnSlotA(initialSlot);
    setGnnSlotB(initialSlot);
    setGnnDataA(null);
    setGnnDataB(null);
    setLogsByAlgo({});
    setActiveAlgo(null);

    try {
      await runClusteringWithProgress(selectedAlgo, dataset, undefined, (evt: ClusterProgressEvent) => {
        if (evt.type === "algo_start" && evt.algorithm) {
          const alg = evt.algorithm;
          setActiveAlgo(alg);
          setLogsByAlgo((prev) => (prev[alg] ? prev : { ...prev, [alg]: [] }));
        } else if (evt.type === "log" && evt.algorithm && evt.line) {
          const alg = evt.algorithm;
          const line = evt.line;
          setLogsByAlgo((prev) => {
            const existing = prev[alg] ?? [];
            return { ...prev, [alg]: [...existing, line].slice(-400) };
          });
        } else if (evt.type === "algo_done" && evt.algorithm && evt.data) {
          const alg = evt.algorithm;
          const data = evt.data;
          setResults((prev) => ({ ...prev, [alg]: data }));

          if (alg !== GNN_ALGO) {
            const tasks = getTasksFromAlgoData(data);
            setPolygonIdx((prev) => ({ ...prev, [alg]: 0 }));
            const firstTaskKey = tasks[0];
            const variants = firstTaskKey ? getVariantsFromAlgoData(data, firstTaskKey) : [];
            const lastVarIdx = variants.length > 0 ? variants.length - 1 : 0;
            setVariantIdx((prev) => ({ ...prev, [alg]: lastVarIdx }));
          }
        } else if (evt.type === "error") {
          console.error("Clustering error:", evt.message);
        }
      });
    } catch (error) {
      console.error("Clustering failed:", error);
      alert(`Clasterization failed: ${error}`);
    } finally {
      if (selectedAlgo.includes(GNN_ALGO)) {
        try {
          const [dataA, dataB] = await Promise.all([
            loadGnnAlgorithmResult(gnnAlgoA),
            loadGnnAlgorithmResult(gnnAlgoB)
          ]);
          setGnnDataA(dataA);
          setGnnDataB(dataB);
        } catch (err) {
          console.error("Failed to load GNN data after run:", err);
        }
      }
      setLoading(false);
      setActiveAlgo(null);
    }
  }, [selectedAlgo, dataset, gnnAlgoA, gnnAlgoB]);

  const handlePolygonChange = (alg: string, newVal: number, max: number) => {
    const clamped = Math.min(Math.max(newVal, 1), max) - 1;
    setPolygonIdx((prev) => ({ ...prev, [alg]: clamped }));

    const algoData = results[alg];
    const tasks = getTasksFromAlgoData(algoData);
    const taskKey = tasks[clamped] || tasks[0];
    const variants = getVariantsFromAlgoData(algoData, taskKey);
    const lastVarIdx = variants.length > 0 ? variants.length - 1 : 0;
    setVariantIdx((prev) => ({ ...prev, [alg]: lastVarIdx }));
  };

  const handleVariantChange = (alg: string, newVal: number, max: number) => {
    const clamped = Math.min(Math.max(newVal, 1), max) - 1;
    setVariantIdx((prev) => ({ ...prev, [alg]: clamped }));
  };

  const handleGnnPolygonChange = (slot: "A" | "B", newVal: number) => {
    const algoData = slot === "A" ? gnnDataA : gnnDataB;
    const tasks = getTasksFromAlgoData(algoData);
    const max = Math.max(tasks.length, 1);
    const clamped = Math.min(Math.max(newVal, 1), max) - 1;
    const taskKey = tasks[clamped] || tasks[0];
    const variants = taskKey ? getVariantsFromAlgoData(algoData, taskKey) : [];
    const lastVarIdx = variants.length > 0 ? variants.length - 1 : 0;
    const setter = slot === "A" ? setGnnSlotA : setGnnSlotB;
    setter({ polygonIdx: clamped, variantIdx: lastVarIdx });
  };

  const handleGnnVariantChange = (slot: "A" | "B", newVal: number) => {
    const algoData = slot === "A" ? gnnDataA : gnnDataB;
    const current = slot === "A" ? gnnSlotA : gnnSlotB;
    const tasks = getTasksFromAlgoData(algoData);
    const taskKey = tasks[current.polygonIdx] || tasks[0];
    const variants = taskKey ? getVariantsFromAlgoData(algoData, taskKey) : [];
    const max = Math.max(variants.length, 1);
    const clamped = Math.min(Math.max(newVal, 1), max) - 1;
    const setter = slot === "A" ? setGnnSlotA : setGnnSlotB;
    setter((prev) => ({ ...prev, variantIdx: clamped }));
  };

  const hasResultsToDisplay = selectedAlgo.some((alg) => results[alg]);
  const hasStartedRun = loading || hasResultsToDisplay;

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-gray-800">Clusterization module</h2>
          {loading && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-500 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-600"></span>
              </span>
              Running…
            </span>
          )}
        </div>
        <button
          onClick={handleRun}
          disabled={loading || selectedAlgo.length === 0}
          className={`inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium shadow-sm
            ${loading || selectedAlgo.length === 0
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

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6 pb-6 border-b border-gray-200">
        <label className="flex flex-col gap-1 text-xs font-medium text-gray-500">
          Dataset
          <select
            value={dataset}
            disabled={loading}
            onChange={(e) => {
              setDataset(e.target.value as "small" | "large" | "big");
              setResults({});
            }}
            className="border border-gray-200 rounded-md px-2 py-1.5 text-sm text-gray-800 bg-white disabled:bg-gray-50"
          >
            <option value="small">small</option>
            <option value="large">large</option>
          </select>
        </label>

        <div className="flex flex-col gap-1 text-xs font-medium text-gray-500">
          Standalone
          <div className="flex flex-wrap items-center gap-3 border border-gray-200 rounded-md px-3 py-1.5 bg-white min-h-[34px]">
            {AVAILABLE_STANDALONE_ALGORITHMS.map((alg) => (
              <label key={alg} className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selectedAlgo.includes(alg)}
                  disabled={loading}
                  onChange={() => toggleAlgorithm(alg)}
                  className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700 font-normal">{alg}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-1 text-xs font-medium text-gray-500 sm:col-span-1">
          <div className="flex items-center gap-1">
            <span>Evolutionary algorithm</span>
            <div className="relative flex items-center group">
              <button type="button" className="text-gray-400 hover:text-gray-600 focus:outline-none">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </button>
              <span className="absolute bottom-full left-0 mb-2 hidden group-hover:block bg-gray-800 text-white text-xs rounded py-1 px-2 w-max max-w-[300px] whitespace-normal shadow-lg z-10">
                Algorithms below are used to initiate initial population for evolutionary algorithm. Does not support dataset choosing.
              </span>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3 border border-gray-200 rounded-md px-3 py-1.5 bg-white min-h-[34px]">
            {AVAILABLE_EVO_ALGORITHMS.map((alg) => (
              <label key={alg} className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selectedAlgo.includes(alg)}
                  disabled={loading}
                  onChange={() => toggleAlgorithm(alg)}
                  className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700 font-normal">{alg}</span>
              </label>
            ))}
          </div>
        </div>
      </div>

      <div className="space-y-6">
        {!hasStartedRun ? (
          <div className="border border-gray-200 rounded-lg p-4">
            <div className="mb-3 text-sm text-gray-500">
              {selectedAlgo.length === 0
                ? "Select at least one algorithm and press Run."
                : "Press Run to execute selected algorithms."}
            </div>
            <ClusterMapCanvas clusters={[]} taskId="" dataset={dataset} />
          </div>
        ) : (
          selectedAlgo.map((alg) => {
            const algoData = results[alg];
            const isActive = activeAlgo === alg;
            const lines = logsByAlgo[alg] ?? [];
            const hasData = getTasksFromAlgoData(algoData).length > 0;

            if (alg === GNN_ALGO) {
              const hasGnnData = (gnnDataA && gnnDataA.length > 0) || (gnnDataB && gnnDataB.length > 0);
              return (
                <div key={alg} className="border border-gray-200 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="text-sm font-medium text-gray-600 bg-gray-100 px-3 py-1 rounded">
                      {alg}
                    </div>
                    <AlgoStatusBadge isActive={isActive} hasData={hasGnnData} />
                  </div>

                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 xl:divide-x xl:divide-gray-200">
                    <div className="xl:pr-6">
                      <div className="mb-3">
                        <label className="flex items-center gap-2 text-xs font-medium text-gray-500">
                          <span>Algorithm A:</span>
                          <select
                            value={gnnAlgoA}
                            disabled={loading}
                            onChange={(e) => setGnnAlgoA(e.target.value)}
                            className="border border-gray-200 rounded-md px-2 py-1 text-sm text-gray-800 bg-white disabled:bg-gray-50"
                          >
                            {GNN_ALGORITHMS.map((algo) => (
                              <option key={algo} value={algo}>
                                {algo.replace(/_/g, " ").replace(/dbscan eps/i, "DBSCAN eps")}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                      <MapSlot
                        slotLabel="A"
                        algoData={gnnDataA}
                        isRunning={isActive}
                        dataset={dataset}
                        state={gnnSlotA}
                        onPolygonChange={(v) => handleGnnPolygonChange("A", v)}
                        onVariantChange={(v) => handleGnnVariantChange("A", v)}
                        costLabel="Total Cost"
                      />
                    </div>
                    <div className="xl:pl-6">
                      <div className="mb-3">
                        <label className="flex items-center gap-2 text-xs font-medium text-gray-500">
                          <span>Algorithm B:</span>
                          <select
                            value={gnnAlgoB}
                            disabled={loading}
                            onChange={(e) => setGnnAlgoB(e.target.value)}
                            className="border border-gray-200 rounded-md px-2 py-1 text-sm text-gray-800 bg-white disabled:bg-gray-50"
                          >
                            {GNN_ALGORITHMS.map((algo) => (
                              <option key={algo} value={algo}>
                                {algo.replace(/_/g, " ").replace(/dbscan eps/i, "DBSCAN eps")}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                      <MapSlot
                        slotLabel="B"
                        algoData={gnnDataB}
                        isRunning={isActive}
                        dataset={dataset}
                        state={gnnSlotB}
                        onPolygonChange={(v) => handleGnnPolygonChange("B", v)}
                        onVariantChange={(v) => handleGnnVariantChange("B", v)}
                        costLabel="Total Cost"
                      />
                    </div>
                  </div>

                  {hasGnnData ? (
                    lines.length > 0 && (
                      <details className="mt-3">
                        <summary className="text-xs text-gray-400 cursor-pointer select-none">
                          Running logs
                        </summary>
                        <RunLogPanel lines={lines} active={false} />
                      </details>
                    )
                  ) : (
                    <RunLogPanel lines={lines} active={isActive} />
                  )}
                </div>
              );
            }

            if (!hasData) {
              return (
                <div key={alg} className="border border-gray-200 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="text-sm font-medium text-gray-600 bg-gray-100 px-3 py-1 rounded">
                      {alg}
                    </div>
                    <AlgoStatusBadge isActive={isActive} hasData={false} />
                  </div>
                  <ClusterMapCanvas clusters={[]} taskId="" dataset={dataset} isRunning={isActive} />
                  <RunLogPanel lines={lines} active={isActive} />
                </div>
              );
            }

            const tasks = getTasksFromAlgoData(algoData);
            const selectedTaskIdx = polygonIdx[alg] ?? 0;

            return (
              <div key={alg} className="border border-gray-200 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="text-sm font-medium text-gray-600 bg-gray-100 px-3 py-1 rounded">
                    {alg}
                  </div>
                  <AlgoStatusBadge isActive={isActive} hasData={true} />
                </div>

                <MapSlot
                  algoData={algoData}
                  isRunning={false}
                  dataset={dataset}
                  state={{ polygonIdx: selectedTaskIdx, variantIdx: variantIdx[alg] ?? 0 }}
                  onPolygonChange={(v) => handlePolygonChange(alg, v, Math.max(tasks.length, 1))}
                  onVariantChange={(v) =>
                    handleVariantChange(
                      alg,
                      v,
                      Math.max(
                        getVariantsFromAlgoData(algoData, tasks[selectedTaskIdx] || tasks[0]).length,
                        1
                      )
                    )
                  }
                  costLabel="Score"
                />

                {lines.length > 0 && (
                  <details className="mt-3">
                    <summary className="text-xs text-gray-400 cursor-pointer select-none">
                      Running logs
                    </summary>
                    <RunLogPanel lines={lines} active={false} />
                  </details>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}