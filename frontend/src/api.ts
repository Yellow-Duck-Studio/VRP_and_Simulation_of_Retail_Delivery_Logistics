export interface WarehouseInfo {
  taskId: number;
  id: number;
  lat: number;
  lon: number;
}

export interface OrderInfo {
  taskId: number;
  id: number;
  warehouseId: number;
  lat: number;
  lon: number;
  pickupReadyAt: string;
  createdAt: string;
  deliveryDeadlineAt: string;
  weight: number;
}

export interface ClusterData {
  cluster_id: number;
  warehouse_id: number;
  transport_type: string;
  order_ids: number[];
}

export interface ClusterizationVariant {
  clusterization_id: number;
  fitness_score: number;
  is_valid: boolean;
  clusters: ClusterData[];
}

export interface GnnClusterData {
  order_ids: (string | number)[];
  feasible: boolean;
  transport: string;
  order_sequence: (string | number)[];
  distance_km: number;
  duration_min: number;
  cost: number;
}

export interface GnnTaskResult {
  task_id: string | number;
  warehouse_id: string | number;
  num_orders: number;
  clusters: GnnClusterData[];
}

export type AlgorithmResults = Record<string, ClusterizationVariant[]> | GnnTaskResult[];

export type AllResults = Record<string, AlgorithmResults>;

// IMPORTANT: order_id in orders.csv is unique only WITHIN a single task_id
// (polygon), not globally. The same order_id appears across many different
// task_id groups with completely different coordinates. Keying the orders
// map by order_id alone causes later polygons to silently overwrite earlier
// ones during load, and causes lookups to return the wrong polygon's data
// (coordinates that don't change when switching polygons). Lookups must use
// the composite (taskId, orderId) key.
function orderKey(taskId: number | string, orderId: number | string): string {
  return `${taskId}_${orderId}`;
}

function normalizeTaskId(taskId: number | string | undefined | null): number {
  if (typeof taskId === "number") return taskId;
  if (!taskId) return NaN;
  const match = taskId.match(/(\d+)/);
  return match ? parseInt(match[0], 10) : NaN;
}

export let orders: Record<string, OrderInfo> = {};

export function getOrder(taskId: number | string, orderId: number | string): OrderInfo | undefined {
  return orders[orderKey(normalizeTaskId(taskId), orderId)];
}

export function getOrdersForTask(taskId: number | string): OrderInfo[] {
  const tId = normalizeTaskId(taskId);
  return Object.values(orders).filter((o) => o.taskId === tId);
}

// Use relative URLs in production (proxied through nginx)
// Set VITE_API_BASE_URL to override for local development (e.g., http://localhost:3001)
const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
export const API_BASE_URL = `${API_BASE}/api`;
export const DATA_BASE_URL = API_BASE || "";
export const WS_BASE_URL = API_BASE ? API_BASE.replace(/^http/, "ws") : "";

export const DATASET_MAPPING = {
  small: {
    orders: `${DATA_BASE_URL}/data/small/orders.csv`,
    warehouses: `${DATA_BASE_URL}/data/small/warehouses.csv`
  },
  large: {
    orders: `${DATA_BASE_URL}/data/large/orders.csv`,
    warehouses: `${DATA_BASE_URL}/data/large/warehouses.csv`
  },
  big: {
    orders: `${DATA_BASE_URL}/data/big/orders-B.csv`,
    warehouses: `${DATA_BASE_URL}/data/big/warehouses-B.csv`
  }
};

export async function loadOrdersDataset(csvUrl: string): Promise<void> {
  try {
    const response = await fetch(csvUrl);
    const text = await response.text();

    const lines = text.trim().split('\n');
    const newOrders: Record<string, OrderInfo> = {};

    for (let i = 1; i < lines.length; i++) {
      const row = lines[i].split(',');
      if (row.length < 9) continue;

      const taskId = parseInt(row[0], 10);
      const orderId = parseInt(row[1], 10);
      newOrders[orderKey(taskId, orderId)] = {
        taskId,
        id: orderId,
        warehouseId: parseInt(row[2], 10),
        lat: parseFloat(row[3]),
        lon: parseFloat(row[4]),
        pickupReadyAt: row[5],
        createdAt: row[6],
        deliveryDeadlineAt: row[7],
        weight: parseFloat(row[8]),
      };
    }

    orders = newOrders;
  } catch (error) {
    console.error("Failed to load or parse orders.csv:", error);
  }
}

export let warehouses: Record<string, WarehouseInfo> = {};

function warehouseKey(taskId: number | string, warehouseId: number | string): string {
  return `${taskId}_${warehouseId}`;
}

export function getWarehousesForTask(taskId: number | string): WarehouseInfo[] {
  const tId = normalizeTaskId(taskId);
  return Object.values(warehouses).filter((w) => w.taskId === tId);
}

export async function loadWarehousesDataset(csvUrl: string = `${DATA_BASE_URL}/data/small/warehouses.csv`): Promise<void> {
  try {
    const response = await fetch(csvUrl);
    const text = await response.text();
    const lines = text.trim().split('\n');
    const newWarehouses: Record<string, WarehouseInfo> = {};
    for (let i = 1; i < lines.length; i++) {
      const row = lines[i].split(',');
      if (row.length < 4) continue;
      const taskId = parseInt(row[0], 10);
      const warehouseId = parseInt(row[1], 10);
      newWarehouses[warehouseKey(taskId, warehouseId)] = {
        taskId,
        id: warehouseId,
        lat: parseFloat(row[2]),
        lon: parseFloat(row[3]),
      };
    }
    warehouses = newWarehouses;
  } catch (error) {
    console.error("Failed to load or parse warehouses.csv:", error);
  }
}

export async function runClustering(algorithms: string[]): Promise<AllResults> {
  const response = await fetch(`${API_BASE_URL}/cluster`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ algorithms }),
  });

  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.error || "Failed to run clustering");
  }

  return await response.json();
}

export interface ClusterProgressEvent {
  type: "algo_start" | "log" | "algo_done" | "error" | "done";
  algorithm?: string;
  line?: string;
  message?: string;
  data?: AlgorithmResults;
  results?: AllResults;
}

export function runClusteringWithProgress(
  algorithms: string[],
  dataset: string,
  gnnAlgorithm: string | undefined,
  onEvent: (event: ClusterProgressEvent) => void
): Promise<AllResults> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const ws = new WebSocket(`${WS_BASE_URL}/ws/cluster`);

    ws.onopen = () => {
      ws.send(JSON.stringify({ algorithms, dataset, gnn_algorithm: gnnAlgorithm }));
    };

    ws.onmessage = (event) => {
      let data: ClusterProgressEvent;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }

      onEvent(data);

      if (data.type === "done") {
        settled = true;
        resolve(data.results || {});
        ws.close();
      } else if (data.type === "error" && !data.algorithm) {
        settled = true;
        reject(new Error(data.message || "Clustering failed"));
        ws.close();
      } else if (data.type === "error" && data.algorithm) {
        // Algorithm-specific error: the server also closes the socket after
        // sending this, so treat it as fatal for the whole run too.
        settled = true;
        reject(new Error(data.message || `Clustering failed for ${data.algorithm}`));
      }
    };
    ws.onerror = () => { if (!settled) { settled = true; reject(new Error("WebSocket connection error")); } };
    ws.onclose = () => { if (!settled) { settled = true; reject(new Error("Connection closed before clustering finished")); } };
  });
}

export interface SimulationConfig {
  input?: string;
  time_step?: number;
  max_steps?: number;
  strict?: boolean;
}

export async function listSimulationInputs(): Promise<string[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/simulate/inputs`);
    if (!response.ok) return ["test_data_innopolis.json"];
    const data = await response.json();
    return data.inputs?.length ? data.inputs : ["test_data_innopolis.json"];
  } catch {
    return ["test_data_innopolis.json"];
  }
}

export async function runSimulation(config: SimulationConfig = {}): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/simulate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(config),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to run simulation");
  }

  return await response.text();
}

export const sortTaskKeys = (keys: string[]): string[] => {
  return [...keys].sort((a, b) => {
    const numA = parseInt(a.replace(/\D/g, ""), 10) || 0;
    const numB = parseInt(b.replace(/\D/g, ""), 10) || 0;
    return numA - numB;
  });
};

export const getTasksFromAlgoData = (algoData: AlgorithmResults): string[] => {
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

export const getVariantsFromAlgoData = (
  algoData: AlgorithmResults,
  taskKey: string
): ClusterizationVariant[] => {
  if (!algoData || !taskKey) return [];

  if (Array.isArray(algoData)) {
    const rawId = taskKey.replace("task_", "");
    const allFound = algoData.filter(
      (item: GnnTaskResult) => String(item.task_id) === taskKey || String(item.task_id) === rawId
    );

    if (allFound.length === 0) return [];

    const mergedClusters = allFound.flatMap((item: GnnTaskResult) =>
      item.clusters.map((c: GnnClusterData) => {
        const sequence = c.order_sequence || c.order_ids || [];

        return {
          order_ids: sequence.map((id: string | number) => Number(id)),
          transport_type: c.transport || "unknown",
          warehouse_id: Number(item.warehouse_id),
        };
      })
    );

    const totalScore = allFound.reduce(
      (acc, item) =>
        acc + item.clusters.reduce((cAcc: number, c: GnnClusterData) => cAcc + (c.cost || 0), 0),
      0
    );

    const isValid = allFound.every((item) =>
      item.clusters.every((c: GnnClusterData) => c.feasible !== false)
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

export interface PredictionFileMeta {
  filename: string;
  algorithm: string;
  eps: number | null;
  label: string;
}

export async function listPredictionFiles(): Promise<PredictionFileMeta[]> {
  const response = await fetch(`${API_BASE_URL}/predictions/list`);
  if (!response.ok) {
    throw new Error("Failed to load predictions manifest");
  }
  const data = await response.json();
  return data.files ?? [];
}

export type PredictionFileContent = GnnTaskResult[] | { error: string };

export async function loadPredictionFilesBatch(
  filenames: string[]
): Promise<Record<string, PredictionFileContent>> {
  const response = await fetch(`${API_BASE_URL}/predictions/batch`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ filenames }),
  });

  if (!response.ok) {
    throw new Error("Failed to load prediction file batch");
  }

  return await response.json();
}

export async function loadGnnAlgorithmResult(algorithm: string): Promise<GnnTaskResult[]> {
  const response = await fetch(`${API_BASE_URL}/gnn/${algorithm}`);

  if (!response.ok) {
    throw new Error(`Failed to load GNN result for algorithm: ${algorithm}`);
  }

  return await response.json();
}