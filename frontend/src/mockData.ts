export interface OrderInfo {
  id: number;
  address: string;
  weight: number;
  volume: number;
  timeWindow: string;
}

export const mockOrders: Record<number, OrderInfo> = {
  10: { id: 10, address: "ул. Ленина, 12", weight: 15, volume: 2.3, timeWindow: "08:00-10:00" },
  2:  { id: 2,  address: "пр. Мира, 45",   weight: 8,  volume: 1.1, timeWindow: "09:00-11:00" },
  67: { id: 67, address: "ул. Пушкина, 7", weight: 22, volume: 3.0, timeWindow: "10:30-12:30" },
  32: { id: 32, address: "пер. Садовый, 3",weight: 5,  volume: 0.8, timeWindow: "07:00-09:00" },
  33: { id: 33, address: "ул. Кирова, 19", weight: 12, volume: 1.9, timeWindow: "08:30-10:30" },
  37: { id: 37, address: "пр. Строителей, 8",weight: 18,volume: 2.5, timeWindow: "09:00-11:00" },
  38: { id: 38, address: "ул. Гагарина, 11", weight: 9, volume: 1.2, timeWindow: "10:00-12:00" },
  40: { id: 40, address: "пер. Заводской, 5",weight: 20,volume: 2.8, timeWindow: "11:00-13:00" },
  28: { id: 28, address: "ул. Советская, 22",weight: 7, volume: 1.0, timeWindow: "08:00-10:00" },
  29: { id: 29, address: "пр. Космонавтов, 4",weight: 14,volume: 2.0, timeWindow: "09:30-11:30" },
};

function generateMockClusterOutput(algorithm: string) {
  const baseTasks: Record<string, number[][][]> = {};

  const tasks = ["task_1", "task_2"];
  tasks.forEach((task) => {
    const variants: number[][][] = [];
    for (let v = 0; v < 3; v++) {
      const clusters: number[][] = [];
      if (v === 0) {
        clusters.push([32, 33, 37, 38, 40]);
        clusters.push([28, 29]);
        clusters.push([10, 2, 67]);
      } else if (v === 1) {
        clusters.push([32, 33]);
        clusters.push([37, 38, 40, 28, 29]);
        clusters.push([10, 67, 2]);
      } else {
        clusters.push([32, 33, 37]);
        clusters.push([38, 40, 28]);
        clusters.push([29, 10, 2, 67]);
      }
      variants.push(clusters);
    }
    baseTasks[task] = variants;
  });

  if (algorithm === "Sweep") {
    baseTasks["task_1"][0] = [[32, 37, 40], [33, 38, 28, 29], [10, 2, 67]];
  }
  return baseTasks;
}

export async function runClustering(algorithms: string[]): Promise<Record<string, any>> {
  await new Promise((res) => setTimeout(res, 1500));
  const results: Record<string, any> = {};
  algorithms.forEach((alg) => {
    results[alg] = generateMockClusterOutput(alg);
  });
  return results;
}

export async function runSimulation(): Promise<string> {
  await new Promise((res) => setTimeout(res, 1200));
  return `Simulation finished successfully.
Total routes: 5
Total distance: 234.5 km
Total cost: 1523.45
Unassigned orders: 0
Detailed report:
  Route 1: [32,33,37] distance=42.1 km
  Route 2: [28,29,38,40] distance=58.3 km
  ...`;
}