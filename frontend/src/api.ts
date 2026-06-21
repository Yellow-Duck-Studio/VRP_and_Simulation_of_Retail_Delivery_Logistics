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

export const API_BASE_URL = "http://localhost:3001/api";
export const DATA_BASE_URL = "http://localhost:3001";

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