import argparse
import time
import torch
import pandas as pd

from config import DEVICE
from io_utils import load_instances, load_transport_types_with_optional_couriers
from data import build_graph, normalize_edge_mass
from model import ClusteringGNN
from decode import decode
from costs import clustering_total_cost


def run(warehouses_csv, orders_csv, transport_csv, solutions_json, model_path,
        limit=None, report_path=None, couriers_csv=None):
    device = torch.device(DEVICE if torch.cuda.is_available() else "cpu")
    tariffs = load_transport_types_with_optional_couriers(transport_csv, couriers_csv=couriers_csv)
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
    records = []  # one row per (task_id, warehouse_id) instance -- the full comparison

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
        decode_ms = (time.time() - t0) * 1000.0
        total_time += decode_ms / 1000.0

        pred_cost = clustering_total_cost(
            inst.warehouse_lat, inst.warehouse_lon, orders_by_id, pred_clusters, tariffs
        )
        gt_cost = None
        if inst.clusters is not None:
            gt_cost = clustering_total_cost(
                inst.warehouse_lat, inst.warehouse_lon, orders_by_id, inst.clusters, tariffs
            )

        ratio = None
        if pred_cost is None:
            print(f"[task {inst.task_id} wh {inst.warehouse_id}] INFEASIBLE prediction (баг в decode/repair)")
        else:
            n_feasible += 1
            if gt_cost is not None and gt_cost > 0:
                ratio = pred_cost / gt_cost
                ratio_sum += ratio
                count += 1

        records.append({
            "task_id": inst.task_id,
            "warehouse_id": inst.warehouse_id,
            "n_orders": len(inst.orders),
            "pred_feasible": pred_cost is not None,
            "pred_cost": pred_cost,
            "gt_cost": gt_cost,
            "ratio": ratio,
            "decode_ms": decode_ms,
        })

    print(f"feasible: {n_feasible}/{n_total}")
    if count:
        print(f"avg cost ratio (pred/optimal): {ratio_sum/count:.4f}")
    print(f"avg decode time per warehouse: {total_time/max(n_total,1)*1000:.1f} ms")

    if not records:
        return pd.DataFrame(records)

    report_df = pd.DataFrame(records)

    # per-task rollup: sums costs across all warehouses of a task, so the
    # ratio reflects task-level performance rather than warehouse-level noise
    comparable = report_df.dropna(subset=["gt_cost", "pred_cost"])
    if not comparable.empty:
        task_summary = (
            comparable.groupby("task_id")
            .agg(n_warehouses=("warehouse_id", "count"),
                 total_pred_cost=("pred_cost", "sum"),
                 total_gt_cost=("gt_cost", "sum"))
            .reset_index()
        )
        task_summary["ratio"] = task_summary["total_gt_cost"] / task_summary["total_pred_cost"]

        print("\n=== per-task comparison (pred vs. optimal) ===")
        print(task_summary.to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    if report_path:
        report_df.to_csv(report_path, index=False)
        print(f"\nDetailed per-warehouse report written to {report_path}")

    return report_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouses", default="data/large/warehouses.csv")
    parser.add_argument("--orders", default="data/large/orders.csv")
    parser.add_argument("--transport", default="data/transport_types.csv")
    parser.add_argument("--solutions", default="data/large/ilp_master.json",
                        help="Optional solutions.json for comparison against a reference partition.")
    parser.add_argument("--couriers", default=None)
    parser.add_argument("--model", default="GNN/model.pt")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--report", default="comparison_report.csv",
                        help="path to write the detailed per-warehouse comparison CSV")
    args = parser.parse_args()
    run(args.warehouses, args.orders, args.transport, args.solutions, args.model,
        args.limit, args.report, args.couriers)
