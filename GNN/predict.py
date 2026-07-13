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
from io_utils import load_instances, load_transport_types
from data import build_graph, normalize_edge_mass
from model import ClusteringGNN
from decode import decode
from costs import best_cluster_solution, clustering_total_cost


def predict(warehouses_csv, orders_csv, transport_csv, model_path, out_path=None, limit=None):
    device = torch.device(DEVICE if torch.cuda.is_available() else "cpu")
    tariffs = load_transport_types(transport_csv)
    min_capacity_kg = min(t.max_payload_kg for t in tariffs)

    model = ClusteringGNN().to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()

    # solutions_json=None -> instances без ground truth, работает и на новых данных
    instances = load_instances(warehouses_csv, orders_csv, solutions_json=None)
    if limit:
        instances = instances[:limit]

    # группировка по task_id: каждый task_id -> список кластеризаций
    # (здесь всегда одна кластеризация на task, т.к. GNN даёт одно решение)
    tasks = {}  # task_id -> {"clusters": [...], "cost_sum": float, "is_valid": bool, "next_cluster_id": int}
    total_time = 0.0
    n_warehouses = 0

    for inst in instances:
        n_warehouses += 1
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

        task_entry = tasks.setdefault(inst.task_id, {
            "clusters": [],
            "cost_sum": 0.0,
            "is_valid": True,
            "next_cluster_id": 1,
        })

        # раскладка по каждому кластеру: транспорт, маршрут, cost
        feasible_wh = True
        for cluster_ids in pred_clusters:
            sol = best_cluster_solution(
                inst.warehouse_lat, inst.warehouse_lon,
                [orders_by_id[oid] for oid in cluster_ids], tariffs,
            )
            if sol is None:
                feasible_wh = False
                task_entry["is_valid"] = False
                task_entry["clusters"].append({
                    "cluster_id": task_entry["next_cluster_id"],
                    "warehouse_id": inst.warehouse_id,
                    "transport_type": None,
                    "order_ids": cluster_ids,
                })
            else:
                task_entry["clusters"].append({
                    "cluster_id": task_entry["next_cluster_id"],
                    "warehouse_id": inst.warehouse_id,
                    "transport_type": sol["transport"],
                    "order_ids": cluster_ids,
                })
                task_entry["cost_sum"] += sol["cost"]
            task_entry["next_cluster_id"] += 1

        total_cost = clustering_total_cost(
            inst.warehouse_lat, inst.warehouse_lon, orders_by_id, pred_clusters, tariffs
        )
        if total_cost is None:
            task_entry["is_valid"] = False

        status = "OK" if (feasible_wh and total_cost is not None) else "INFEASIBLE"
        print(f"[task {inst.task_id} wh {inst.warehouse_id}] {status} | "
              f"{len(inst.orders)} заказов -> {len(pred_clusters)} кластеров")

    # финальная сборка в требуемый формат
    output = {}
    for task_id, entry in tasks.items():
        output[f"task_{task_id}"] = [{
            "clusterization_id": 1,
            "fitness_score": round(entry["cost_sum"], 4),
            "is_valid": entry["is_valid"],
            "clusters": entry["clusters"],
        }]

    n_ok = sum(1 for entry in tasks.values() if entry["is_valid"])
    print(f"\nВсего складов: {n_warehouses}, задач: {len(tasks)}, допустимых задач: {n_ok}")
    if n_warehouses:
        print(f"среднее время decode на склад: {total_time/n_warehouses*1000:.1f} мс")

    if out_path:
        with open(out_path, "w") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"результаты сохранены в {out_path}")

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouses", required=False, default="../data/large/warehouses.csv", )
    parser.add_argument("--orders", required=False, default="../data/large/orders.csv", )
    parser.add_argument("--transport", required=False, default="../data/transport_types.csv", )
    parser.add_argument("--model", default="../GNN/model.pt")
    parser.add_argument("--out", default="predictions.json")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    predict(args.warehouses, args.orders, args.transport, args.model, args.out, args.limit)