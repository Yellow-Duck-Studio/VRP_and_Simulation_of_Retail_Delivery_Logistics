import argparse
import time

import torch

from config import DEVICE
from io_utils import load_instances, load_transport_types
from data import build_graph, normalize_edge_mass
from model import ClusteringGNN
from decode import decode
from costs import clustering_total_cost


def run(warehouses_csv, orders_csv, transport_csv, solutions_json, model_path, limit=None):
    device = torch.device(DEVICE if torch.cuda.is_available() else "cpu")
    tariffs = load_transport_types(transport_csv)
    min_capacity_kg = min(t.max_payload_kg for t in tariffs)

    model = ClusteringGNN().to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()

    instances = load_instances(warehouses_csv, orders_csv, solutions_json)
    if limit:
        instances = instances[:limit]

    n_feasible, n_total = 0, 0
    ratio_sum, count = 0.0, 0
    total_time = 0.0

    for inst in instances:
        if len(inst.orders) < 2:
            continue
        n_total += 1
        orders_by_id = {o["order_id"]: o for o in inst.orders}

        graph = build_graph(inst)
        graph.edge_attr = normalize_edge_mass(graph.edge_attr, min_capacity_kg)
        graph = graph.to(device)

        t0 = time.time()
        pred_clusters = decode(model, graph, orders_by_id, inst.warehouse_lat, inst.warehouse_lon, tariffs)
        total_time += time.time() - t0

        pred_cost = clustering_total_cost(
            inst.warehouse_lat, inst.warehouse_lon, orders_by_id, pred_clusters, tariffs
        )
        if pred_cost is None:
            print(f"[task {inst.task_id} wh {inst.warehouse_id}] INFEASIBLE prediction (баг в decode/repair)")
            continue
        n_feasible += 1

        if inst.clusters is not None:
            gt_cost = clustering_total_cost(
                inst.warehouse_lat, inst.warehouse_lon, orders_by_id, inst.clusters, tariffs
            )
            if gt_cost is not None and gt_cost > 0:
                ratio_sum += pred_cost / gt_cost
                count += 1

    print(f"feasible: {n_feasible}/{n_total}")
    if count:
        print(f"avg cost ratio (pred/optimal): {ratio_sum/count:.4f}")
    print(f"avg decode time per warehouse: {total_time/max(n_total,1)*1000:.1f} ms")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouses", required=True)
    parser.add_argument("--orders", required=True)
    parser.add_argument("--transport", required=True)
    parser.add_argument("--solutions", default=None, help="опционально: solutions.json для сравнения с оптимумом солвера")
    parser.add_argument("--model", default="model.pt")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(args.warehouses, args.orders, args.transport, args.solutions, args.model, args.limit)