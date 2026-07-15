import { useState, useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import {
  listPredictionFiles,
  loadPredictionFilesBatch,
  getTasksFromAlgoData,
  getVariantsFromAlgoData,
  type PredictionFileMeta,
  type GnnTaskResult,
} from "../api.ts";
import ClusterMapCanvas from "./ClusterMapCanvas";

interface PanelState {
  filename: string;
  data: GnnTaskResult[] | null;
  loading: boolean;
  error: string | null;
  polygonIdx: number;
  variantIdx: number;
}

const emptyPanel = (filename = ""): PanelState => ({
  filename,
  data: null,
  loading: false,
  error: null,
  polygonIdx: 0,
  variantIdx: 0,
});

interface GnnPredictionsCompareProps {
  dataset: string;
  // Bumped by the parent whenever a live run finishes, so freshly written
  // predictions_*.json files show up in the picker without a page reload.
  refreshKey?: number;
}

// Two independent map panels, side by side, so a person can put e.g. "Clarke
// Wright" next to "DBSCAN (eps=0.3)" and actually read both maps at once,
// instead of squinting at a grid of a dozen tiny ones.
export default function GnnPredictionsCompare({ dataset, refreshKey = 0 }: GnnPredictionsCompareProps) {
  const [files, setFiles] = useState<PredictionFileMeta[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [panelA, setPanelA] = useState<PanelState>(emptyPanel());
  const [panelB, setPanelB] = useState<PanelState>(emptyPanel());

  // Only auto-pick defaults for panel A/B the first time files show up.
  // On later refreshes (triggered by refreshKey after a run) we just update
  // the list of options and leave whatever the person already has open alone.
  const hasInitializedPanels = useRef(false);

  useEffect(() => {
    let cancelled = false;
    // Background refreshes (refreshKey changing after the first load)
    // shouldn't blank out the maps the person is currently looking at.
    if (!hasInitializedPanels.current) setListLoading(true);
    listPredictionFiles()
      .then((metas) => {
        if (cancelled) return;
        setFiles(metas);
        setListError(null);
        if (!hasInitializedPanels.current && metas.length > 0) {
          hasInitializedPanels.current = true;
          // Sensible defaults: first file into panel A, second (if any) into
          // panel B, so there's already something to compare on first render.
          setPanelA(emptyPanel(metas[0].filename));
          if (metas.length > 1) setPanelB(emptyPanel(metas[1].filename));
        }
      })
      .catch((err) => {
        if (!cancelled) setListError(err instanceof Error ? err.message : "Failed to load list");
      })
      .finally(() => {
        if (!cancelled) setListLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (listLoading) {
    return <div className="text-sm text-gray-500 p-4">Loading GNN predictions list...</div>;
  }
  if (listError) {
    return <div className="text-sm text-red-600 p-4">Failed to load predictions: {listError}</div>;
  }
  if (files.length === 0) {
    return (
      <div className="text-sm text-gray-500 p-4">
        No prediction files found in <code className="bg-gray-100 px-1 rounded">data/</code>.
      </div>
    );
  }

  return (
    <div className="border border-gray-200 rounded-lg p-4">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 xl:divide-x xl:divide-gray-200">
        <div className="xl:pr-6">
          <GnnMapPanel label="Map A" files={files} panel={panelA} setPanel={setPanelA} dataset={dataset} />
        </div>
        <div className="xl:pl-6">
          <GnnMapPanel label="Map B" files={files} panel={panelB} setPanel={setPanelB} dataset={dataset} />
        </div>
      </div>
    </div>
  );
}

function GnnMapPanel({
  label,
  files,
  panel,
  setPanel,
  dataset,
}: {
  label: string;
  files: PredictionFileMeta[];
  panel: PanelState;
  setPanel: Dispatch<SetStateAction<PanelState>>;
  dataset: string;
}) {
  // Load the selected file's content whenever the filename changes.
  useEffect(() => {
    if (!panel.filename) return;
    let cancelled = false;
    setPanel((prev) => ({ ...prev, loading: true, error: null, data: null }));

    loadPredictionFilesBatch([panel.filename])
      .then((results) => {
        if (cancelled) return;
        const result = results[panel.filename];
        if (!result) {
          setPanel((prev) => ({ ...prev, loading: false, error: "No data returned" }));
          return;
        }
        if ("error" in result) {
          setPanel((prev) => ({ ...prev, loading: false, error: result.error }));
          return;
        }
        setPanel((prev) => ({ ...prev, loading: false, data: result, polygonIdx: 0, variantIdx: 0 }));
      })
      .catch((err) => {
        if (cancelled) return;
        setPanel((prev) => ({
          ...prev,
          loading: false,
          error: err instanceof Error ? err.message : "Failed to load file",
        }));
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [panel.filename]);

  const tasks = panel.data ? getTasksFromAlgoData(panel.data) : [];
  const taskKey = tasks[panel.polygonIdx] ?? tasks[0];
  const variants = panel.data ? getVariantsFromAlgoData(panel.data, taskKey) : [];
  const variant = variants[panel.variantIdx];
  const clusters = variant ? variant.clusters : [];

  const handlePolygonChange = (value: number) => {
    const clamped = Math.min(Math.max(value, 1), Math.max(tasks.length, 1)) - 1;
    setPanel((prev) => ({ ...prev, polygonIdx: clamped, variantIdx: 0 }));
  };

  const handleVariantChange = (value: number) => {
    const clamped = Math.min(Math.max(value, 1), Math.max(variants.length, 1)) - 1;
    setPanel((prev) => ({ ...prev, variantIdx: clamped }));
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-600 bg-gray-100 px-3 py-1 rounded">{label}</span>
          <select
            value={panel.filename}
            onChange={(e) => setPanel(emptyPanel(e.target.value))}
            className="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm px-2 py-1"
          >
            {files.map((f) => (
              <option key={f.filename} value={f.filename}>
                {f.label}
              </option>
            ))}
          </select>
        </div>

        {panel.data && (
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-gray-500">Polygon</span>
              <input
                type="number"
                min={1}
                max={Math.max(tasks.length, 1)}
                value={panel.polygonIdx + 1}
                onChange={(e) => handlePolygonChange(parseInt(e.target.value, 10) || 1)}
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
                value={panel.variantIdx + 1}
                onChange={(e) => handleVariantChange(parseInt(e.target.value, 10) || 1)}
                className="w-16 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm px-2 py-1"
              />
              <span className="text-xs text-gray-400">/ {variants.length}</span>
            </div>

            {variant?.fitness_score !== undefined && (
              <span className="text-xs px-2 py-0.5 rounded font-medium bg-emerald-100 text-emerald-700">
                Cost: {variant.fitness_score.toFixed(2)}
              </span>
            )}
          </div>
        )}
      </div>

      {panel.loading ? (
        <div className="flex items-center justify-center min-h-[400px] border border-dashed border-gray-200 rounded-lg bg-slate-50">
          <span className="text-xs text-gray-400 animate-pulse">Loading...</span>
        </div>
      ) : panel.error ? (
        <div className="flex items-center justify-center min-h-[400px] border border-dashed border-red-200 rounded-lg bg-red-50/50">
          <span className="text-xs text-red-500 px-4 text-center">{panel.error}</span>
        </div>
      ) : !taskKey ? (
        <div className="flex items-center justify-center min-h-[400px] border border-dashed border-gray-200 rounded-lg bg-slate-50">
          <span className="text-xs text-gray-400">No polygons found in this file</span>
        </div>
      ) : (
        <ClusterMapCanvas clusters={clusters} taskId={taskKey} dataset={dataset} />
      )}
    </div>
  );
}