import { useState, useCallback, useRef, useEffect } from "react";
import { PlayIcon } from "@heroicons/react/24/solid";
import { runClusteringWithProgress, type ClusterProgressEvent, type AlgorithmResults, type AllResults, type GnnTaskResult, type GnnClusterData, type ClusterizationVariant } from "../api.ts";
import ClusterMapCanvas from "./ClusterMapCanvas";

const AVAILABLE_EVO_ALGORITHMS = ["DBScan", "Clarke Wright", "Sweep", "Destroy & Repair", "Random"];
const AVAILABLE_STANDALONE_ALGORITHMS = ["GNN"];

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

const sortTaskKeys = (keys: string[]) => {
  return [...keys].sort((a, b) => {
    const numA = parseInt(a.replace(/\D/g, "")) || 0;
    const numB = parseInt(b.replace(/\D/g, "")) || 0;
    return numA - numB;
  });
};

const getTasksFromAlgoData = (algoData: AlgorithmResults): string[] => {
  if (!algoData) return [];
  if (Array.isArray(algoData)) {
    const keys = algoData.map((item: GnnTaskResult) => {
      const id = item.task_id;
      return typeof id === "string" && id.startsWith("task_") ? id : `task_${id}`;
    });
    return sortTaskKeys([...new Set(keys)]);
  }
  return sortTaskKeys(Object.keys(algoData));
};

const getVariantsFromAlgoData = (algoData: AlgorithmResults, taskKey: string): ClusterizationVariant[] => {
  if (!algoData || !taskKey) return [];

  if (Array.isArray(algoData)) {
    const rawId = taskKey.replace("task_", "");
    const allFound = algoData.filter(
      (item: GnnTaskResult) => String(item.task_id) === taskKey || String(item.task_id) === rawId
    );

    if (allFound.length === 0) return [];

    let clusterId = 0;
    const mergedClusters = allFound.flatMap((item: GnnTaskResult) =>
      item.clusters.map((c: GnnClusterData) => {
        const sequence = c.order_sequence || c.order_ids || [];
        const orderIds = sequence.map((id: string | number) => Number(id));

        return {
          cluster_id: ++clusterId,
          order_ids: orderIds,
          transport_type: c.transport || "unknown",
          warehouse_id: Number(item.warehouse_id)
        };
      })
    );

    const totalScore = allFound.reduce((acc, item) =>
      acc + item.clusters.reduce((cAcc: number, c: GnnClusterData) => cAcc + (c.cost || 0), 0)
    , 0);

    const isValid = allFound.every(item =>
      item.clusters.every((c: GnnClusterData) => c.feasible)
    );

    return [
      {
        clusterization_id: 1,
        fitness_score: totalScore,
        is_valid: isValid,
        clusters: mergedClusters,
      },
    ];
  }

  return (algoData as Record<string, ClusterizationVariant[]>)[taskKey] || [];
};

export default function ClusterizationModule() {
  const [selectedAlgo, setSelectedAlgo] = useState<string[]>([]);
  const [results, setResults] = useState<AllResults>({});
  const [loading, setLoading] = useState(false);
  const [activeAlgo, setActiveAlgo] = useState<string | null>(null);
  const [logsByAlgo, setLogsByAlgo] = useState<Record<string, string[]>>({});
  const [dataset, setDataset] = useState<"small" | "large" | "big">("small");

  const [polygonIdx, setPolygonIdx] = useState<Record<string, number>>({});
  const [variantIdx, setVariantIdx] = useState<Record<string, number>>({});

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
    setLogsByAlgo({});
    setActiveAlgo(null);

    try {
      await runClusteringWithProgress(selectedAlgo, dataset, (evt: ClusterProgressEvent) => {
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
          setPolygonIdx((prev) => ({ ...prev, [alg]: 0 }));

          const tasks = getTasksFromAlgoData(data);
          const firstTaskKey = tasks[0];
          const variants = getVariantsFromAlgoData(data, firstTaskKey);
          const lastVarIdx = variants.length > 0 ? variants.length - 1 : 0;
          setVariantIdx((prev) => ({ ...prev, [alg]: lastVarIdx }));
        } else if (evt.type === "error") {
          console.error("Clustering error:", evt.message);
        }
      });
    } catch (error) {
      console.error("Clustering failed:", error);
      alert(`Clasterization failed: ${error}`);
    } finally {
      setLoading(false);
    }
  }, [selectedAlgo, dataset]);

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

  const hasResultsToDisplay = selectedAlgo.some((alg) => results[alg]);
  const hasStartedRun = loading || hasResultsToDisplay;

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">Clusterization module</h2>
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

      <div className="flex flex-col lg:flex-row gap-6">
        <div className="w-full lg:w-56 flex-shrink-0">
          <div className="mb-8">
            <label className="block text-sm font-medium text-gray-700 mb-3">Datasets</label>
            <div className="inline-flex p-1 space-x-1 bg-gray-100/80 border border-gray-200 rounded-xl shadow-inner">
              {(["small", "large"] as const).map((size) => (
                <button
                  key={size}
                  onClick={() => {
                    setDataset(size);
                    setResults({});
                  }}
                  disabled={loading}
                  className={`
                    relative w-24 py-1.5 text-center text-sm font-medium rounded-lg capitalize transition-all duration-200 ease-in-out
                    ${
                      dataset === size
                        ? "bg-white text-blue-600 shadow-sm ring-1 ring-black/5"
                        : "text-gray-500 hover:text-gray-800 hover:bg-gray-200/50"
                    }
                    ${loading ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
                  `}
                >
                  {size}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-1 mb-2">
            <label className="block text-sm font-medium text-gray-700">Standalone</label>
          </div>
          <div className="relative flex items-center group space-y-2">
            {AVAILABLE_STANDALONE_ALGORITHMS.map((alg) => (
              <label key={alg} className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selectedAlgo.includes(alg)}
                  onChange={() => toggleAlgorithm(alg)}
                  className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">{alg}</span>
              </label>
            ))}
          </div>

          <div className="flex items-center gap-1 mb-2 pt-5">
            <label className="block text-sm font-medium text-gray-700">Evolutionary algorithm</label>
            <div className="relative flex items-center group">
              <button type="button" className="text-gray-400 hover:text-gray-600 focus:outline-none">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </button>

              <span className="absolute bottom-full left-20/2 -translate-x-1/2 mb-2 hidden group-hover:block bg-gray-800 text-white text-xs rounded py-1 px-2 w-max max-w-[300px] whitespace-normal shadow-lg">
                Algorithms below are used to initiate initial population for evolutionary algorithm. Does not support dataset choosing.
              </span>
            </div>
          </div>

          <div className="space-y-2">
            {AVAILABLE_EVO_ALGORITHMS.map((alg) => (
              <label key={alg} className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selectedAlgo.includes(alg)}
                  onChange={() => toggleAlgorithm(alg)}
                  className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">{alg}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="flex-1 space-y-6">
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
              const tasks = getTasksFromAlgoData(algoData);

              if (tasks.length === 0) {
                const isActive = activeAlgo === alg;
                const lines = logsByAlgo[alg] ?? [];
                return (
                  <div key={alg} className="border border-gray-200 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-3">
                      <div className="text-sm font-medium text-gray-600 bg-gray-100 px-3 py-1 rounded">
                        {alg}
                      </div>
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${isActive ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-500"}`}>
                        {isActive ? "Running" : "In queue"}
                      </span>
                    </div>
                    <ClusterMapCanvas clusters={[]} taskId="" dataset={dataset} isRunning />
                    <RunLogPanel lines={lines} active={isActive} />
                  </div>
                );
              }

              const selectedTaskIdx = polygonIdx[alg] ?? 0;
              const selectedTaskKey = tasks[selectedTaskIdx] || tasks[0];
              const variants = getVariantsFromAlgoData(algoData, selectedTaskKey);
              const selectedVarIdx = variantIdx[alg] ?? 0;

              const selectedVariant = variants[selectedVarIdx];
              const selectedVariantClusters = selectedVariant
                ? selectedVariant.clusters
                : [];

              const lines = logsByAlgo[alg] ?? [];

              return (
                <div key={alg} className="border border-gray-200 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-4">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs text-gray-500">Polygon</span>
                        <input
                          type="number"
                          min={1}
                          max={tasks.length}
                          value={selectedTaskIdx + 1}
                          onChange={(e) =>
                            handlePolygonChange(alg, parseInt(e.target.value) || 1, tasks.length)
                          }
                          className="w-16 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm px-2 py-1"
                        />
                        <span className="text-xs text-gray-400">/ {tasks.length}</span>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <span className="text-xs text-gray-500">Variant</span>
                        <input
                          type="number"
                          min={1}
                          max={variants.length}
                          value={selectedVarIdx + 1}
                          onChange={(e) =>
                            handleVariantChange(alg, parseInt(e.target.value) || 1, variants.length)
                          }
                          className="w-16 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm px-2 py-1"
                        />
                        <span className="text-xs text-gray-400">/ {variants.length}</span>

                        {selectedVariant?.fitness_score !== undefined && (
                          <span className="text-xs ml-3 px-2 py-0.5 rounded font-medium bg-emerald-100 text-emerald-700">
                            {alg === "GNN"
                              ? `Total Cost: ${selectedVariant.fitness_score.toFixed(2)}`
                              : `Score: ${selectedVariant.fitness_score.toFixed(2)}`
                            }
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="text-sm font-medium text-gray-600 bg-gray-100 px-3 py-1 rounded">
                      {alg}
                    </div>
                  </div>

                  <ClusterMapCanvas clusters={selectedVariantClusters} taskId={selectedTaskKey} dataset={dataset} />

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
    </div>
  );
}