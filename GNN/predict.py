"""
Прогон обученной модели на новых (или тестовых) данных: для каждого склада
выдаёт разбиение на кластеры + честный cost (с выбором лучшего тарифа и
порядка объезда через costs.py — то же самое, чем считает солвер).

Пример:
    python predict.py \
        --warehouses warehouses.csv \
        --orders orders.csv \
        --transport transport_types.csv \
        --model model.pt \
        --out predictions.json

Если в orders.csv/warehouses.csv несколько task_id — обработает все разом.
Ground truth (solutions.json) НЕ нужен для этого скрипта — используй
infer.py, если хочешь сравнить с оптимумом солвера.
"""

"""
Прогон обученной модели на новых (или тестовых) данных с использованием
пайплайна из нескольких алгоритмов (Greedy, DBSCAN, Clarke-Wright, Sweep).
"""

import argparse
import json
import time

import torch

from config import DEVICE, DEFAULT_MAX_COURIERS
from io_utils import load_instances, load_transport_types
from data import build_graph, normalize_edge_mass
from model import ClusteringGNN
from decode import decode
from costs import best_cluster_solution, clustering_total_cost

# 10 configurations to output 10 unique json files
PIPELINE_ALGOS = {
    "greedy": {"algorithm": "greedy"},
    "clarke_wright": {"algorithm": "clarke_wright"},
    "sweep": {"algorithm": "sweep"},
    "dbscan_eps_0.1": {"algorithm": "dbscan", "eps": 0.1},
    "dbscan_eps_0.2": {"algorithm": "dbscan", "eps": 0.2},
    "dbscan_eps_0.4": {"algorithm": "dbscan", "eps": 0.4},
    "dbscan_eps_0.5": {"algorithm": "dbscan", "eps": 0.5},
    "dbscan_eps_0.6": {"algorithm": "dbscan", "eps": 0.6},
    "dbscan_eps_0.8": {"algorithm": "dbscan", "eps": 0.8},
    "dbscan_eps_0.9": {"algorithm": "dbscan", "eps": 0.9},
}

def predict(warehouses_csv, orders_csv, transport_csv, model_path, out_prefix="predictions", limit=None, algorithm=None):
    device = torch.device(DEVICE if torch.cuda.is_available() else "cpu")
    tariffs = load_transport_types(transport_csv)
    min_capacity_kg = min(t.max_payload_kg for t in tariffs)

    model = ClusteringGNN().to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()

    instances = load_instances(warehouses_csv, orders_csv, solutions_json=None)
    if limit:
        instances = instances[:limit]

    # Prebuild graphs to avoid doing it 10 times per instance
    graphs_cache = {}
    for inst in instances:
        if len(inst.orders) >= 2:
            graph = build_graph(inst, default_max_couriers=DEFAULT_MAX_COURIERS)
            graph.edge_attr = normalize_edge_mass(graph.edge_attr, min_capacity_kg)
            graphs_cache[inst.task_id, inst.warehouse_id] = graph.to(device)

    # Run pipeline for each algorithm config
    algos_to_run = {algorithm: PIPELINE_ALGOS[algorithm]} if algorithm else PIPELINE_ALGOS
    for algo_name, algo_kwargs in algos_to_run.items():
        print(f"\n{'='*50}\nЗапуск пайплайна для алгоритма: {algo_name}\n{'='*50}")
        results = []
        total_time = 0.0

        for inst in instances:
            orders_by_id = {o["order_id"]: o for o in inst.orders}

            if len(inst.orders) < 2:
                pred_clusters = [[oid] for oid in orders_by_id]
            else:
                graph = graphs_cache[inst.task_id, inst.warehouse_id]
                t0 = time.time()
                pred_clusters = decode(
                    model, graph, orders_by_id,
                    inst.warehouse_lat, inst.warehouse_lon,
                    tariffs, max_couriers=inst.max_couriers,
                    **algo_kwargs
                )
                total_time += time.time() - t0

            cluster_details = []
            feasible = True
            for cluster_ids in pred_clusters:
                sol = best_cluster_solution(
                    inst.warehouse_lat, inst.warehouse_lon,
                    [orders_by_id[oid] for oid in cluster_ids], tariffs,
                )
                if sol is None:
                    feasible = False
                    cluster_details.append({"order_ids": cluster_ids, "feasible": False})
                else:
                    cluster_details.append({
                        "order_ids": cluster_ids,
                        "feasible": True,
                        "transport": sol["transport"],
                        "order_sequence": sol["order_sequence"],
                        "distance_km": round(sol["distance_km"], 4),
                        "duration_min": round(sol["duration_min"], 2),
                        "cost": round(sol["cost"], 4),
                    })

            total_cost = clustering_total_cost(
                inst.warehouse_lat, inst.warehouse_lon, orders_by_id, pred_clusters, tariffs
            )

            result = {
                "task_id": inst.task_id,
                "warehouse_id": inst.warehouse_id,
                "num_orders": len(inst.orders),
                "clusters": cluster_details,
                "total_cost": round(total_cost, 4) if total_cost is not None else None,
                "feasible": feasible and total_cost is not None,
            }
            results.append(result)

            status = "OK" if result["feasible"] else "INFEASIBLE"
            print(f"[task {inst.task_id} wh {inst.warehouse_id}] {status} | "
                  f"{len(inst.orders)} заказов -> {len(pred_clusters)} кластеров | "
                  f"cost={result['total_cost']}")

        n_ok = sum(1 for r in results if r["feasible"])
        print(f"\nВсего складов: {len(results)}, допустимых разбиений ({algo_name}): {n_ok}")
        if results:
            print(f"Среднее время decode на склад: {total_time/len(results)*1000:.1f} мс")

        # If a specific algorithm was requested, output directly to the prefix path
        # Otherwise, append algorithm name to prefix
        if algorithm:
            out_path = f"{out_prefix}.json"
        else:
            out_path = f"{out_prefix}_{algo_name}.json"
        with open(out_path, "w") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"Результаты {algo_name} сохранены в {out_path}")

    return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouses", required=False, default="../data/large/warehouses.csv")
    parser.add_argument("--orders", required=False, default="../data/large/orders.csv")
    parser.add_argument("--transport", required=False, default="../data/transport_types.csv")
    parser.add_argument("--model", default="../GNN/model.pt")
    parser.add_argument("--out-prefix", default="predictions")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--algorithm", default=None, choices=list(PIPELINE_ALGOS.keys()))
    args = parser.parse_args()
    predict(args.warehouses, args.orders, args.transport, args.model, args.out_prefix, args.limit, args.algorithm)