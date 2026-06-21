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

export let orders: Record<number, OrderInfo> = {};

export const API_BASE_URL = "http://localhost:3001/api";
export const DATA_BASE_URL = "http://localhost:3001";

export async function loadOrdersDataset(csvUrl: string = `${DATA_BASE_URL}/data/orders.csv`): Promise<void> {
  try {
    const response = await fetch(csvUrl);
    const text = await response.text();

    const lines = text.trim().split('\n');
    const newOrders: Record<number, OrderInfo> = {};

    for (let i = 1; i < lines.length; i++) {
      const row = lines[i].split(',');
      if (row.length < 9) continue;

      const orderId = parseInt(row[1], 10);
      newOrders[orderId] = {
        taskId: parseInt(row[0], 10),
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