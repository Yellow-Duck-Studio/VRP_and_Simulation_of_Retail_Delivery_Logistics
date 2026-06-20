import { useState, useCallback } from "react";
import { PlayIcon } from "@heroicons/react/24/solid";
import { runClustering } from "../mockData";
import ClusterMapCanvas from "./ClusterMapCanvas";

const AVAILABLE_ALGORITHMS = ["DBScan", "Clarke Wright", "Sweep"];

export default function ClusterizationModule() {
  const [selectedAlgo, setSelectedAlgo] = useState<string[]>([]);
  const [results, setResults] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(false);

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
    const data = await runClustering(selectedAlgo);
    setResults(data);

    const initPoly: Record<string, number> = {};
    const initVar: Record<string, number> = {};
    selectedAlgo.forEach((alg) => {
      const tasks = Object.keys(data[alg]).sort();
      initPoly[alg] = 0;
      initVar[alg] = 0;
    });
    setPolygonIdx(initPoly);
    setVariantIdx(initVar);
    setLoading(false);
  }, [selectedAlgo]);

  const getTasks = (alg: string) => {
    const algRes = results[alg];
    if (!algRes) return [];
    return Object.keys(algRes).sort();
  };

  const getVariants = (alg: string, taskKey: string) => {
    const algRes = results[alg];
    if (!algRes || !algRes[taskKey]) return [];
    return algRes[taskKey];
  };

  const handlePolygonChange = (alg: string, newVal: number, max: number) => {
    const clamped = Math.min(Math.max(newVal, 1), max) - 1;
    setPolygonIdx((prev) => ({ ...prev, [alg]: clamped }));
    setVariantIdx((prev) => ({ ...prev, [alg]: 0 }));
  };

  const handleVariantChange = (alg: string, newVal: number, max: number) => {
    const clamped = Math.min(Math.max(newVal, 1), max) - 1;
    setVariantIdx((prev) => ({ ...prev, [alg]: clamped }));
  };

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
          <div className="flex items-center gap-1 mb-2">
            <label className="block text-sm font-medium text-gray-700">
              Algorithms
            </label>

            <div className="relative flex items-center group">
              <button
                type="button"
                className="text-gray-400 hover:text-gray-600 focus:outline-none"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </button>

              <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block bg-gray-800 text-white text-xs rounded py-1 px-2 w-max max-w-[300px] whitespace-normal shadow-lg">
                Algorithms below are used to initiate initial population for evolutionary algorithm.
              </span>
            </div>
          </div>
          <div className="space-y-2">
            {AVAILABLE_ALGORITHMS.map((alg) => (
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
          {selectedAlgo.length === 0 && (
            <p className="text-sm text-gray-400 italic">Select at least one algorithm and press Run.</p>
          )}

          {selectedAlgo.map((alg) => {
            const tasks = getTasks(alg);
            if (tasks.length === 0) return null;
            const selectedTaskIdx = polygonIdx[alg] ?? 0;
            const selectedTaskKey = tasks[selectedTaskIdx] || tasks[0];
            const variants = getVariants(alg, selectedTaskKey);
            const selectedVarIdx = variantIdx[alg] ?? 0;
            const selectedVariantClusters = variants[selectedVarIdx] || [];

            return (
              <div key={alg} className="border border-gray-200 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-4">
                    {/* Polygon */}
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

                    {/* Variant */}
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
                    </div>
                  </div>
                  <div className="text-sm font-medium text-gray-600 bg-gray-100 px-3 py-1 rounded">
                    {alg}
                  </div>
                </div>

                <ClusterMapCanvas clusters={selectedVariantClusters} width={700} height={500} />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}