"""
Скрипт инференса и статистического сравнения всех 10 конфигураций декодирования
(Greedy, Clarke-Wright, Sweep, DBSCAN c разными eps) относительно оптимума ILP.

Запуск:
    python infer.py
"""

import argparse
import math
import time
import numpy as np
import pandas as pd
import torch

try:
    from scipy import stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from config import DEVICE, DEFAULT_MAX_COURIERS
from io_utils import load_instances, load_transport_types
from data import build_graph, normalize_edge_mass
from model import ClusteringGNN
from decode import decode
from costs import clustering_total_cost, best_cluster_solution, required_couriers

# 10 алгоритмических конфигураций декодирования
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


def run_evaluation(warehouses_csv, orders_csv, transport_csv, solutions_json, model_path,
                   limit=None, report_path=None, max_couriers=None):
    device = torch.device(DEVICE if torch.cuda.is_available() else "cpu")
    tariffs = load_transport_types(transport_csv)
    min_capacity_kg = min(t.max_payload_kg for t in tariffs)

    model = ClusteringGNN().to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()

    instances = load_instances(warehouses_csv, orders_csv, solutions_json)
    if limit:
        instances = instances[:limit]

    # Исключаем тривиальные инстанции (< 2 заказов)
    instances = [inst for inst in instances if len(inst.orders) >= 2]
    if not instances:
        print("Нет валидных инстансов для оценки.")
        return pd.DataFrame(), pd.DataFrame()

    print(f"Загружено {len(instances)} инстансов складов для тестирования 10 алгоритмов...\n")

    # Предокэшируем графы для избавления от лишних вычислений при повторных прогонах
    graphs_cache = {}
    for inst in instances:
        effective_max_couriers = max_couriers or inst.max_couriers or DEFAULT_MAX_COURIERS
        graph = build_graph(inst, default_max_couriers=effective_max_couriers)
        graph.edge_attr = normalize_edge_mass(graph.edge_attr, min_capacity_kg)
        graphs_cache[inst.task_id, inst.warehouse_id] = (graph.to(device), effective_max_couriers)

    all_records = []

    # Оценка каждой алгоритмической конфигурации
    for algo_name, algo_kwargs in PIPELINE_ALGOS.items():
        print(f"Оценка алгоритма: {algo_name:18} ...", end="", flush=True)

        for inst in instances:
            orders_by_id = {o["order_id"]: o for o in inst.orders}
            graph, effective_max_couriers = graphs_cache[inst.task_id, inst.warehouse_id]

            t0 = time.time()
            pred_clusters = decode(
                model, graph, orders_by_id, inst.warehouse_lat, inst.warehouse_lon, tariffs,
                max_couriers=effective_max_couriers, **algo_kwargs
            )
            decode_ms = (time.time() - t0) * 1000.0

            pred_cost = clustering_total_cost(
                inst.warehouse_lat, inst.warehouse_lon, orders_by_id, pred_clusters, tariffs
            )

            pred_required_couriers = None
            if pred_cost is not None:
                pred_sols = [
                    best_cluster_solution(inst.warehouse_lat, inst.warehouse_lon,
                                          [orders_by_id[o] for o in c], tariffs)
                    for c in pred_clusters
                ]
                if all(s is not None for s in pred_sols):
                    pred_required_couriers = required_couriers(pred_sols)

            gt_cost = None
            if inst.clusters is not None:
                gt_cost = clustering_total_cost(
                    inst.warehouse_lat, inst.warehouse_lon, orders_by_id, inst.clusters, tariffs
                )

            ratio = (pred_cost / gt_cost) if (pred_cost is not None and gt_cost is not None and gt_cost > 0) else None

            all_records.append({
                "algo": algo_name,
                "task_id": inst.task_id,
                "warehouse_id": inst.warehouse_id,
                "n_orders": len(inst.orders),
                "max_couriers": effective_max_couriers,
                "pred_required_couriers": pred_required_couriers,
                "pred_feasible": pred_cost is not None,
                "pred_cost": pred_cost,
                "gt_cost": gt_cost,
                "ratio": ratio,
                "decode_ms": decode_ms,
            })
        print(" Готово.")

    df = pd.DataFrame(all_records)

    # ==================== СТАТИСТИЧЕСКИЙ АНАЛИЗ ====================
    summary_rows = []
    baseline_ratios = df[df["algo"] == "greedy"].set_index(["task_id", "warehouse_id"])["ratio"]

    for algo_name in PIPELINE_ALGOS.keys():
        sub = df[df["algo"] == algo_name]
        n_total = len(sub)
        n_feasible = sub["pred_feasible"].sum()
        feasibility_rate = (n_feasible / n_total) * 100.0 if n_total > 0 else 0.0

        ratios = sub["ratio"].dropna()

        if not ratios.empty:
            mean_ratio = ratios.mean()
            std_ratio = ratios.std()
            median_ratio = ratios.median()
            q25 = ratios.quantile(0.25)
            q75 = ratios.quantile(0.75)
            iqr = q75 - q25

            # Статистический p-value (Paired t-test & Wilcoxon test) против Greedy
            curr_ratios = sub.set_index(["task_id", "warehouse_id"])["ratio"]
            paired = pd.concat([baseline_ratios, curr_ratios], axis=1, keys=["base", "curr"]).dropna()

            if algo_name == "greedy" or paired.empty or not HAS_SCIPY:
                p_val_ttest = float("nan")
                p_val_wilcoxon = float("nan")
            else:
                _, p_val_ttest = stats.ttest_rel(paired["curr"], paired["base"])
                try:
                    _, p_val_wilcoxon = stats.wilcoxon(paired["curr"], paired["base"])
                except Exception:
                    p_val_wilcoxon = float("nan")
        else:
            mean_ratio = std_ratio = median_ratio = iqr = float("nan")
            p_val_ttest = p_val_wilcoxon = float("nan")

        avg_latency = sub["decode_ms"].mean()

        summary_rows.append({
            "Algorithm": algo_name,
            "Feasible (%)": round(feasibility_rate, 1),
            "Mean Ratio": round(1/mean_ratio, 4) if not math.isnan(mean_ratio) else None,
            "Std Dev": round(std_ratio, 4) if not math.isnan(std_ratio) else None,
            "Median Ratio": round(1/median_ratio, 4) if not math.isnan(median_ratio) else None,
            "IQR": round(iqr, 4) if not math.isnan(iqr) else None,
            "p-value (t-test)": round(p_val_ttest, 4) if not math.isnan(p_val_ttest) else "N/A",
            "p-value (Wilcoxon)": round(p_val_wilcoxon, 4) if not math.isnan(p_val_wilcoxon) else "N/A",
            "Latency (ms)": round(avg_latency, 2),
        })

    summary_df = pd.DataFrame(summary_rows)

    # Вывод результатов
    print("\n" + "=" * 100)
    print("      ИТОГОВЫЙ СТАТИСТИЧЕСКИЙ ОТЧЕТ СРАВНЕНИЯ АЛГОРИТМОВ ДЕКОДИРОВАНИЯ (PRED / OPTIMAL)")
    print("=" * 100)
    print(summary_df.to_string(index=False))
    print("=" * 100)
    print(" Примечание: Mean/Median Ratio = gt_cost / pred_cost (чем ближе к 1.00, тем лучше).")
    print("             p-value рассчитывается относительно базового алгоритма Greedy.\n")

    if report_path:
        df.to_csv(report_path, index=False)
        print(f"Полные поскладочные данные сохранены в {report_path}")

    return df, summary_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouses", required=False, default="data/large/warehouses.csv")
    parser.add_argument("--orders", required=False, default="data/large/orders.csv")
    parser.add_argument("--transport", required=False, default="data/transport_types.csv")
    parser.add_argument("--solutions", default="data/large/ilp_master.json",
                        help="solutions.json для сравнения с оптимумом солвера")
    parser.add_argument("--model", default="GNN/model.pt")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--report", default="full_comparison_report.csv",
                        help="Путь сохранения подробного CSV отчета")
    parser.add_argument("--max-couriers", type=int, default=None,
                        help="Штат курьеров на смену.")
    args = parser.parse_args()

    run_evaluation(args.warehouses, args.orders, args.transport, args.solutions, args.model,
                   args.limit, args.report, args.max_couriers)