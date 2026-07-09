"""
Scalable EXACT solver for the courier clustering problem.

Same optimality guarantee as the small-scale bitmask-DP solver, but scales to
much larger per-warehouse order counts (e.g. 30 orders/warehouse), by:

  1. Vectorized (numpy) enumeration of every candidate cluster (subset of
     size 1..5) together with its cheapest feasible (transport, visiting
     order) - the SAME brute-force cost computation as before, just batched
     across all subsets/permutations with numpy instead of Python loops.

  2. Combining candidate clusters into a full partition via an EXACT integer
     program (set-partitioning): choose a subset of candidate clusters such
     that every order is covered exactly once and total cost is minimized.
     Solved with scipy.optimize.milp (HiGHS, bundled with scipy - no network
     needed). This is still an exact optimum, not a heuristic - it replaces
     the bitmask DP (which needs 2^n states and can't handle n=30) with an
     ILP formulation of the identical problem.

Cost model, feasibility rules, etc. are unchanged from brute_force_solver.py.
"""

import numpy as np
import pandas as pd
import itertools
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import csr_matrix
import json
import time

EARTH_R_KM = 6371.0088


def haversine_vec(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(a))


def load_data(orders_path, warehouses_path, transport_path):
    # task_id/warehouse_id/order_id forced to str at load time -- otherwise
    # pandas silently upcasts these ID columns to float64 (e.g. "1" -> 1.0)
    # if it encounters any NaN in the column, which corrupts the string keys
    # written into the master archive (e.g. "1.0" instead of "1") and breaks
    # lookups in io_utils.py's _match_solution. Same bug as in
    # brute_force_solver.py, fixed the same way.
    id_dtypes = {"task_id": str, "warehouse_id": str}
    orders = pd.read_csv(orders_path, dtype={**id_dtypes, "order_id": str})
    warehouses = pd.read_csv(warehouses_path, dtype=id_dtypes)
    transports = pd.read_csv(transport_path)

    # Convert to epoch seconds robustly, regardless of which datetime64
    # resolution pandas picks (ns/us/ms/s can differ across pandas versions
    # and environments, e.g. local pandas 3.0 uses "us", Colab may use "ns").
    UNIT_TO_DIVISOR = {"s": 1, "ms": 1e3, "us": 1e6, "ns": 1e9}

    pickup_dt = pd.to_datetime(orders["pickup_ready_at"])
    deadline_dt = pd.to_datetime(orders["delivery_deadline_at"])

    def _divisor_for(dt_series):
        unit = getattr(dt_series.dt, "unit", "ns")  # pandas < 2.0 has no .dt.unit -> always ns
        return UNIT_TO_DIVISOR[unit]

    orders["pickup_ready_epoch"] = pickup_dt.astype("int64") / _divisor_for(pickup_dt)
    orders["deadline_epoch"] = deadline_dt.astype("int64") / _divisor_for(deadline_dt)

    return orders, warehouses, transports.to_dict("records")


def enumerate_candidate_clusters(order_ids, lat, lon, pickup_ready_epoch, deadline_epoch,
                                  mass, wh_lat, wh_lon, transports, max_k=5):
    """
    Vectorized enumeration of all candidate clusters (subsets of size 1..max_k).
    Returns list of dicts: {order_ids: [...], cost: float, transport: str}
    Only feasible clusters are returned.
    """
    n = len(order_ids)
    dist_wh = haversine_vec(wh_lat, wh_lon, lat, lon).astype(np.float32)
    dist_matrix = haversine_vec(lat[:, None], lon[:, None], lat[None, :], lon[None, :]).astype(np.float32)

    candidates = []

    for k in range(1, min(max_k, n) + 1):
        combos = np.array(list(itertools.combinations(range(n), k)), dtype=np.int32)
        n_comb = combos.shape[0]
        if k == 1:
            perm_patterns = np.array([[0]], dtype=np.int32)
        else:
            perm_patterns = np.array(list(itertools.permutations(range(k))), dtype=np.int32)
        n_perm = perm_patterns.shape[0]

        seq_idx = combos[:, perm_patterns]  # (n_comb, n_perm, k)

        mass_combo = mass[combos].sum(axis=1)               # (n_comb,)
        start_epoch = pickup_ready_epoch[combos].max(axis=1)  # (n_comb,)

        # running cumulative distance (transport independent)
        cur_dist = dist_wh[seq_idx[:, :, 0]].astype(np.float32)  # (n_comb, n_perm)
        best_cost = np.full((n_comb,), np.inf, dtype=np.float64)
        best_transport_idx = np.full((n_comb,), -1, dtype=np.int32)
        best_perm_idx = np.full((n_comb,), -1, dtype=np.int32)

        # precompute per-position order index arrays and leg distances once
        leg_list = [dist_wh[seq_idx[:, :, 0]]]
        for i in range(1, k):
            leg_list.append(dist_matrix[seq_idx[:, :, i - 1], seq_idx[:, :, i]])

        cum_dist_per_pos = []
        running = np.zeros((n_comb, n_perm), dtype=np.float32)
        for i in range(k):
            running = running + leg_list[i]
            cum_dist_per_pos.append(running.copy())
        total_dist = cum_dist_per_pos[-1]  # (n_comb, n_perm)

        deadline_per_pos = [deadline_epoch[seq_idx[:, :, i]] for i in range(k)]

        for t_idx, t in enumerate(transports):
            mass_ok = mass_combo <= t["max_payload_kg"] + 1e-9  # (n_comb,)
            if not mass_ok.any():
                continue
            speed = t["approx_speed_kmh"]

            feasible = np.ones((n_comb, n_perm), dtype=bool)
            for i in range(k):
                arrival = start_epoch[:, None] + (cum_dist_per_pos[i] / speed) * 3600.0
                feasible &= arrival <= deadline_per_pos[i]

            feasible &= mass_ok[:, None]

            cost = (t["fixed_fee"]
                    + t["per_km_fee"] * total_dist.astype(np.float64)
                    + t["per_order_fee"] * k
                    + t["per_kg_min_fee"] * mass_combo[:, None])
            cost = np.where(feasible, cost, np.inf)

            perm_best_idx = np.argmin(cost, axis=1)
            perm_best_cost = cost[np.arange(n_comb), perm_best_idx]

            improve = perm_best_cost < best_cost
            best_cost = np.where(improve, perm_best_cost, best_cost)
            best_transport_idx = np.where(improve, t_idx, best_transport_idx)
            best_perm_idx = np.where(improve, perm_best_idx, best_perm_idx)

        valid = np.isfinite(best_cost)
        valid_rows = np.nonzero(valid)[0]

        for row in valid_rows:
            perm_i = best_perm_idx[row]
            seq = seq_idx[row, perm_i, :]
            t = transports[best_transport_idx[row]]
            candidates.append({
                "order_ids": [order_ids[i] for i in seq],
                "cost": float(best_cost[row]),
                "transport": t["code"],
            })

    return candidates


def solve_warehouse_ilp(order_ids, lat, lon, pickup_ready_epoch, deadline_epoch,
                         mass, wh_lat, wh_lon, transports, max_k=5, verbose=False):
    n = len(order_ids)
    t0 = time.time()
    candidates = enumerate_candidate_clusters(
        order_ids, lat, lon, pickup_ready_epoch, deadline_epoch, mass,
        wh_lat, wh_lon, transports, max_k
    )
    if verbose:
        print(f"    candidate clusters: {len(candidates)} (enum time {time.time()-t0:.2f}s)")

    if not candidates:
        return None

    order_id_to_idx = {oid: i for i, oid in enumerate(order_ids)}

    n_cand = len(candidates)
    costs = np.array([c["cost"] for c in candidates], dtype=np.float64)

    rows, cols = [], []
    for j, c in enumerate(candidates):
        for oid in c["order_ids"]:
            rows.append(order_id_to_idx[oid])
            cols.append(j)
    data = np.ones(len(rows), dtype=np.float64)
    A = csr_matrix((data, (rows, cols)), shape=(n, n_cand))

    constraints = LinearConstraint(A, lb=1, ub=1)  # exact cover: each order exactly once
    bounds = Bounds(0, 1)
    integrality = np.ones(n_cand)

    t0 = time.time()
    res = milp(c=costs, constraints=constraints, bounds=bounds, integrality=integrality)
    if verbose:
        print(f"    ILP solve time: {time.time()-t0:.2f}s, status: {res.message}")

    if not res.success:
        return None

    chosen = np.nonzero(res.x > 0.5)[0]
    clusters = [candidates[j] for j in chosen]
    total_cost = sum(c["cost"] for c in clusters)

    return {"total_cost": total_cost, "clusters": clusters}


def main(orders_path, warehouses_path, transport_path, out_prefix, max_k=5, verbose=True):
    orders, warehouses, transports = load_data(orders_path, warehouses_path, transport_path)

    results = {}
    summary_rows = []

    for task_id, task_orders in orders.groupby("task_id"):
        wh_task = warehouses[warehouses["task_id"] == task_id]
        results[str(task_id)] = {}
        for _, wrow in wh_task.iterrows():
            wh_id = wrow["warehouse_id"]
            wh_orders = task_orders[task_orders["warehouse_id"] == wh_id]
            n = len(wh_orders)
            if verbose:
                print(f"Task {task_id} Warehouse {wh_id} (n={n})...")

            sol = solve_warehouse_ilp(
                order_ids=wh_orders["order_id"].tolist(),
                lat=wh_orders["order_lat"].to_numpy(),
                lon=wh_orders["order_lon"].to_numpy(),
                pickup_ready_epoch=wh_orders["pickup_ready_epoch"].to_numpy(),
                deadline_epoch=wh_orders["deadline_epoch"].to_numpy(),
                mass=wh_orders["total_mass_kg"].to_numpy(),
                wh_lat=wrow["lat"], wh_lon=wrow["lon"],
                transports=transports, max_k=max_k, verbose=verbose,
            )

            if sol is None:
                print(f"  -> INFEASIBLE")
                results[str(task_id)][str(wh_id)] = None
                summary_rows.append({"task_id": task_id, "warehouse_id": wh_id, "n_orders": n,
                                      "n_clusters": None, "total_cost": None, "status": "infeasible"})
                continue

            results[str(task_id)][str(wh_id)] = sol
            print(f"  -> clusters={len(sol['clusters'])}, cost={sol['total_cost']:.2f}")
            summary_rows.append({"task_id": task_id, "warehouse_id": wh_id, "n_orders": n,
                                  "n_clusters": len(sol["clusters"]),
                                  "total_cost": round(sol["total_cost"], 2), "status": "ok"})

    with open(f"{out_prefix}_clusterizations.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(f"{out_prefix}_summary.csv", index=False)

    # master_clusterizations.json-compatible archive -- kept grouped by
    # warehouse_id (order_id is only unique WITHIN a task, so flattening
    # trips across warehouses loses the info needed to recover which
    # warehouse a trip belongs to; see build_master_archive() in
    # brute_force_solver.py for the identical fix)
    master_archive = {}
    for task_id, wh_results in results.items():
        by_warehouse, any_infeasible = {}, False
        for wh_id, sol in wh_results.items():
            if sol is None:
                any_infeasible = True
                continue
            trips = [[int(oid) for oid in cluster["order_ids"]] for cluster in sol["clusters"]]
            by_warehouse[str(wh_id)] = trips
        if any_infeasible:
            continue
        master_archive[f"task_{task_id}"] = by_warehouse

    with open(f"{out_prefix}_master.json", "w") as f:
        json.dump(master_archive, f, indent=4, ensure_ascii=False)

    print("\n=== TOTAL OPTIMAL COST PER TASK ===")
    print(summary_df.groupby("task_id")["total_cost"].sum())
    print("\nGrand total:", summary_df["total_cost"].sum())

    return results, summary_df


if __name__ == "__main__":
    import sys
    main(
        "../data/large/orders-L.csv",
        "../data/large/warehouses-L.csv",
        "../data/transport_types.csv",
        "ilp",
    )
