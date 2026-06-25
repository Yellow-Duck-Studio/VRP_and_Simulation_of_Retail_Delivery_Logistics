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

// The clustering backend returns polygon/task keys as "task_2", "task_10", etc,
// while orders.csv has the bare numeric task_id (2, 10, ...). Strip any non-digit
// prefix so both sides resolve to the same numeric id.
function normalizeTaskId(taskId: number | string): number {
  if (typeof taskId === "number") return taskId;
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

export async function loadOrdersDataset(csvUrl: string = `${DATA_BASE_URL}/data/orders.csv`): Promise<void> {
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

export async function loadWarehousesDataset(csvUrl: string = `${DATA_BASE_URL}/data/warehouses.csv`): Promise<void> {
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

export async function runClustering(algorithms: string[]): Promise<Record<string, never>> {
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
  data?: Record<string, never>;
  results?: Record<string, never>;
}

/**
 * Runs the requested algorithms via the /ws/cluster WebSocket endpoint and
 * streams live progress (subprocess log lines, per-algorithm completion)
 * through `onEvent` as it happens. Resolves with the same combined results
 * shape as `runClustering` once everything is done.
 */
export function runClusteringWithProgress(
  algorithms: string[],
  onEvent: (event: ClusterProgressEvent) => void
): Promise<Record<string, never>> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const ws = new WebSocket(`${WS_BASE_URL}/ws/cluster`);

    ws.onopen = () => {
      ws.send(JSON.stringify({ algorithms }));
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

    ws.onerror = () => {
      if (!settled) {
        settled = true;
        reject(new Error("WebSocket connection error"));
      }
    };

    ws.onclose = () => {
      if (!settled) {
        settled = true;
        reject(new Error("Connection closed before clustering finished"));
      }
    };
  });
}

export async function runSimulation(): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/simulate`, {
    method: "POST",
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to run simulation");
  }

  return await response.text();
}