"""
Exact brute-force solver for the courier clustering problem.

For every warehouse (within every task_id) it finds the PROVABLY OPTIMAL
partition of orders into clusters (<=5 orders each), where for every
candidate cluster the cheapest feasible (transport, visiting order) is
found by full enumeration (all transports x all permutations of orders).

The partition-selection step uses an exact bitmask DP over subsets, which
is mathematically equivalent to enumerating every possible partition of
the order set (same optimum), but avoids recomputing the same cluster's
cost multiple times across different partitions.

Cost model (matches the Kaggle checker exactly):
    cost = fixed_fee + per_km_fee * route_distance
                      + per_order_fee * order_count
                      + per_kg_min_fee * route_kg   (route_kg = sum of masses)

route_distance = sum of Haversine legs: warehouse -> order_1 -> ... -> order_k
                 (no return trip to warehouse)
departure time  = max(pickup_ready_at) over all orders in the cluster
feasibility     = cluster weight <= transport max_payload_kg
                  AND arrival time at every order <= its delivery_deadline_at
"""

import pandas as pd
import numpy as np
from itertools import permutations
from datetime import datetime
from math import radians, sin, cos, asin, sqrt
import json
import time

EARTH_R_KM = 6371.0088


def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_R_KM * asin(sqrt(a))


def parse_dt(s):
    return datetime.fromisoformat(s)


def load_data(orders_path, warehouses_path, transport_path):
    # task_id/warehouse_id/order_id forced to str at load time -- otherwise
    # pandas silently upcasts these ID columns to float64 (e.g. "1" -> 1.0)
    # if it encounters any NaN in the column, which corrupts the string keys
    # written into master_clusterizations_bruteforce.json (e.g. "1.0" instead
    # of "1") and breaks lookups in io_utils.py's _match_solution.
    id_dtypes = {"task_id": str, "warehouse_id": str}
    orders = pd.read_csv(orders_path, dtype={**id_dtypes, "order_id": str})
    warehouses = pd.read_csv(warehouses_path, dtype=id_dtypes)
    transports = pd.read_csv(transport_path)

    orders["pickup_ready_at"] = orders["pickup_ready_at"].apply(parse_dt)
    orders["delivery_deadline_at"] = orders["delivery_deadline_at"].apply(parse_dt)

    transport_list = transports.to_dict("records")
    return orders, warehouses, transport_list


def best_cluster_cost(order_rows, wh_lat, wh_lon, transports, max_cluster_size=5):
    """
    order_rows: list of dicts with order_id, order_lat, order_lon,
                pickup_ready_at, delivery_deadline_at, total_mass_kg
    Returns (best_cost, best_transport_code, best_sequence_order_ids) or (None, None, None) if infeasible.
    """
    k = len(order_rows)
    if k == 0 or k > max_cluster_size:
        return None, None, None

    total_mass = sum(o["total_mass_kg"] for o in order_rows)
    start_time = max(o["pickup_ready_at"] for o in order_rows)

    best_cost = None
    best_transport = None
    best_seq = None

    for t in transports:
        if total_mass > t["max_payload_kg"] + 1e-9:
            continue
        speed = t["approx_speed_kmh"]

        for perm in permutations(order_rows):
            cur_lat, cur_lon = wh_lat, wh_lon
            cur_time = start_time
            total_dist = 0.0
            feasible = True
            for o in perm:
                d = haversine(cur_lat, cur_lon, o["order_lat"], o["order_lon"])
                total_dist += d
                travel_hours = d / speed
                arrival = cur_time + pd.Timedelta(hours=travel_hours)
                if arrival > o["delivery_deadline_at"]:
                    feasible = False
                    break
                cur_time = arrival
                cur_lat, cur_lon = o["order_lat"], o["order_lon"]

            if not feasible:
                continue

            cost = (t["fixed_fee"]
                    + t["per_km_fee"] * total_dist
                    + t["per_order_fee"] * k
                    + t["per_kg_min_fee"] * total_mass)

            if best_cost is None or cost < best_cost - 1e-9:
                best_cost = cost
                best_transport = t["code"]
                best_seq = [o["order_id"] for o in perm]

    return best_cost, best_transport, best_seq


def solve_warehouse(order_rows, wh_lat, wh_lon, transports, max_cluster_size=5):
    """
    order_rows: list of order dicts for this warehouse (n <= ~10-12 expected)
    Returns dict: total_cost, clusters: [{order_ids, transport, cost, sequence}]
    Exact optimum via bitmask DP over all subsets.
    """
    n = len(order_rows)
    idx = list(range(n))

    # Precompute cost for every candidate subset (size 1..max_cluster_size)
    from itertools import combinations
    subset_cost = {}       # mask -> cost
    subset_info = {}       # mask -> (transport, seq_order_ids)

    for size in range(1, max_cluster_size + 1):
        if size > n:
            break
        for combo in combinations(idx, size):
            mask = 0
            for i in combo:
                mask |= (1 << i)
            rows = [order_rows[i] for i in combo]
            cost, transport, seq = best_cluster_cost(rows, wh_lat, wh_lon, transports, max_cluster_size)
            if cost is not None:
                subset_cost[mask] = cost
                subset_info[mask] = (transport, seq)

    FULL = (1 << n) - 1
    dp = [None] * (1 << n)
    choice = [None] * (1 << n)  # best first-cluster-mask used to reach this mask
    dp[0] = 0.0

    for mask in range(1, 1 << n):
        # lowest set bit must be covered by the chosen cluster (avoids double counting)
        low = mask & (-mask)
        low_bit_index = low.bit_length() - 1
        sub = mask
        best = None
        best_choice = None
        # enumerate all submasks of mask that contain low_bit_index
        s = mask
        while True:
            if (s & low) and s in subset_cost:
                rem = mask ^ s
                if dp[rem] is not None:
                    cand = subset_cost[s] + dp[rem]
                    if best is None or cand < best - 1e-9:
                        best = cand
                        best_choice = s
            if s == 0:
                break
            s = (s - 1) & mask
        dp[mask] = best
        choice[mask] = best_choice

    if dp[FULL] is None:
        return None  # infeasible warehouse (checker would error out)

    # reconstruct
    clusters = []
    mask = FULL
    while mask:
        s = choice[mask]
        transport, seq = subset_info[s]
        clusters.append({
            "order_ids": seq,
            "transport": transport,
            "cost": subset_cost[s],
        })
        mask ^= s

    return {"total_cost": dp[FULL], "clusters": clusters}


def build_master_archive(results):
    """
    Convert our per-warehouse optimal solutions into a master archive that
    keeps warehouse boundaries intact:
        { "task_1": { "1": [ [order_id, ...], ... ],   # warehouse_id -> trips
                       "2": [ [order_id, ...], ... ] },
          ... }
    order_id is only unique WITHIN a task (it resets/repeats across tasks),
    so trips must stay grouped by warehouse_id here rather than being
    flattened -- otherwise downstream consumers (e.g. infer.py's per-
    warehouse comparison against ground truth) have no way to recover which
    warehouse a trip belongs to.
    """
    master_archive = {}
    for task_id, wh_results in results.items():
        by_warehouse = {}
        any_infeasible = False
        for wh_id, sol in wh_results.items():
            if sol is None:
                any_infeasible = True
                continue
            trips = [[int(oid) for oid in cluster["order_ids"]] for cluster in sol["clusters"]]
            by_warehouse[str(wh_id)] = trips
        if any_infeasible:
            print(f"WARNING: task {task_id} has an infeasible warehouse; "
                  f"skipped from master archive.")
            continue
        master_archive[f"task_{task_id}"] = by_warehouse

    with open("data/master_clusterizations_bruteforce.json", "w") as f:
        json.dump(master_archive, f, indent=4, ensure_ascii=False)

    return master_archive


def main():
    orders, warehouses, transports = load_data(
        "data/orders.csv",
        "data/warehouses.csv",
        "data/transport_types.csv",
    )

    results = {}  # task_id -> warehouse_id -> solution
    summary_rows = []

    for task_id, task_orders in orders.groupby("task_id"):
        wh_task = warehouses[warehouses["task_id"] == task_id]
        results[str(task_id)] = {}
        for _, wrow in wh_task.iterrows():
            wh_id = wrow["warehouse_id"]
            wh_lat, wh_lon = wrow["lat"], wrow["lon"]
            wh_orders = task_orders[task_orders["warehouse_id"] == wh_id]
            order_rows = wh_orders.to_dict("records")
            n = len(order_rows)

            sol = solve_warehouse(order_rows, wh_lat, wh_lon, transports)
            if sol is None:
                print(f"Task {task_id} Warehouse {wh_id}: INFEASIBLE (n={n})")
                results[str(task_id)][str(wh_id)] = None
                summary_rows.append({
                    "task_id": task_id, "warehouse_id": wh_id, "n_orders": n,
                    "n_clusters": None, "total_cost": None, "status": "infeasible"
                })
                continue

            results[str(task_id)][str(wh_id)] = sol
            print(f"Task {task_id} Warehouse {wh_id}: n={n}, "
                  f"clusters={len(sol['clusters'])}, cost={sol['total_cost']:.2f}")
            summary_rows.append({
                "task_id": task_id, "warehouse_id": wh_id, "n_orders": n,
                "n_clusters": len(sol["clusters"]),
                "total_cost": round(sol["total_cost"], 2),
                "status": "ok"
            })

    with open("data/optimal_clusterizations.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv("data/optimal_summary.csv", index=False)

    build_master_archive(results)

    print("\n=== TOTAL OPTIMAL COST PER TASK ===")
    task_totals = summary_df.groupby("task_id")["total_cost"].sum()
    print(task_totals)
    print("\nGrand total (sum over all tasks & warehouses):", summary_df["total_cost"].sum())


if __name__ == "__main__":
    t = time.time()
    main()
    t = time.time() - t
    print("\nElapsed time: ", t, " seconds.")