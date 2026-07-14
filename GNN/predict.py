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

import argparse
import json
import time

import torch

from config import DEVICE
from config import DEFAULT_MAX_COURIERS
from io_utils import load_instances, load_transport_types_with_optional_couriers
from data import build_graph, normalize_edge_mass
from model import ClusteringGNN
from decode import decode
from costs import best_cluster_solution, clustering_total_cost


def predict(warehouses_csv, orders_csv, transport_csv, model_path, out_path=None, limit=None, couriers_csv=None):
    device = torch.device(DEVICE if torch.cuda.is_available() else "cpu")
    tariffs = load_transport_types_with_optional_couriers(transport_csv, couriers_csv=couriers_csv)
    min_capacity_kg = min(t.max_payload_kg for t in tariffs)

    model = ClusteringGNN().to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()

    # solutions_json=None -> instances без ground truth, работает и на новых данных
    instances = load_instances(warehouses_csv, orders_csv, solutions_json=None)
    if limit:
        instances = instances[:limit]

    results = []
    total_time = 0.0

    for inst in instances:
        orders_by_id = {o["order_id"]: o for o in inst.orders}

        # склад с 1 заказом — тривиальный случай, GNN не нужна
        if len(inst.orders) < 2:
            pred_clusters = [[oid] for oid in orders_by_id]
        else:
            graph = build_graph(inst, default_max_couriers=DEFAULT_MAX_COURIERS)
            graph.edge_attr = normalize_edge_mass(graph.edge_attr, min_capacity_kg)
            graph = graph.to(device)

            t0 = time.time()
            pred_clusters = decode(model, graph, orders_by_id, inst.warehouse_lat, inst.warehouse_lon, tariffs)
            total_time += time.time() - t0

        # раскладка по каждому кластеру: транспорт, маршрут, cost
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
    print(f"\nВсего складов: {len(results)}, допустимых разбиений: {n_ok}")
    if results:
        print(f"среднее время decode на склад: {total_time/len(results)*1000:.1f} мс")

    if out_path:
        with open(out_path, "w") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"результаты сохранены в {out_path}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouses", default="data/large/warehouses.csv")
    parser.add_argument("--orders", default="data/large/orders.csv")
    parser.add_argument("--transport", default="data/transport_types.csv")
    parser.add_argument("--couriers", default=None)
    parser.add_argument("--model", default="GNN/model.pt")
    parser.add_argument("--out", default="predictions.json")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    predict(args.warehouses, args.orders, args.transport, args.model, args.out, args.limit, args.couriers)
