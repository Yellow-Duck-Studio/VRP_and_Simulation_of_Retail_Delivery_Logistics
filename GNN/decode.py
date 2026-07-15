"""Affinity-логиты по рёбрам -> валидное разбиение заказов на кластеры."""

import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import torch
from sklearn.cluster import DBSCAN

from config import MAX_CLUSTER_SIZE
from costs import best_cluster_solution, required_couriers
from io_utils import TransportTariff


def greedy_correlation_clustering(order_ids: List[str], affinity: Dict[tuple, float]) -> List[List[str]]:
    parent = {oid: oid for oid in order_ids}
    size = {oid: 1 for oid in order_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pairs = sorted(affinity.items(), key=lambda kv: -kv[1])
    for (a, b), score in pairs:
        if score <= 0:
            break
        ra, rb = find(a), find(b)
        if ra == rb:
            continue
        if size[ra] + size[rb] > MAX_CLUSTER_SIZE:
            continue
        parent[ra] = rb
        size[rb] += size[ra]

    groups: Dict[str, List[str]] = {}
    for oid in order_ids:
        r = find(oid)
        groups.setdefault(r, []).append(oid)
    return list(groups.values())


def dbscan_clustering(order_ids: List[str], affinity: Dict[tuple, float], eps: float) -> List[List[str]]:
    """DBSCAN using 0.5 - affinity as the precomputed distance metric."""
    n = len(order_ids)
    if n == 0: return []
    if n == 1: return [[order_ids[0]]]

    oid_to_idx = {oid: i for i, oid in enumerate(order_ids)}

    # Distance matrix: max distance is 1.0 (when affinity is -0.5)
    dist_matrix = np.ones((n, n))
    np.fill_diagonal(dist_matrix, 0.0)

    for (a, b), score in affinity.items():
        if a in oid_to_idx and b in oid_to_idx:
            i, j = oid_to_idx[a], oid_to_idx[b]
            dist = 0.5 - score  # Maps affinity [-0.5, 0.5] to distance [1.0, 0.0]
            dist_matrix[i, j] = dist
            dist_matrix[j, i] = dist

    clustering = DBSCAN(eps=eps, min_samples=1, metric="precomputed").fit(dist_matrix)

    groups = {}
    for oid, label in zip(order_ids, clustering.labels_):
        # Noise (label -1) is treated as individual clusters in this context
        group_key = f"noise_{oid}" if label == -1 else str(label)
        groups.setdefault(group_key, []).append(oid)

    return list(groups.values())


def clarke_wright_clustering(order_ids: List[str], affinity: Dict[tuple, float]) -> List[List[str]]:
    """Clarke-Wright Savings heuristic adapted for clustering using affinities as savings."""
    routes = {oid: [oid] for oid in order_ids}

    pairs = sorted(affinity.items(), key=lambda kv: -kv[1])
    for (a, b), score in pairs:
        if score <= 0:
            continue

        route_id_a, route_id_b = None, None
        for rid, r in routes.items():
            if a in r: route_id_a = rid
            if b in r: route_id_b = rid

        if route_id_a == route_id_b or route_id_a is None or route_id_b is None:
            continue

        route_a = routes[route_id_a]
        route_b = routes[route_id_b]

        if len(route_a) + len(route_b) > MAX_CLUSTER_SIZE:
            continue

        # Clarke-Wright strictly requires nodes to be at the endpoints of the current routes
        is_a_end = (a == route_a[0] or a == route_a[-1])
        is_b_end = (b == route_b[0] or b == route_b[-1])

        if is_a_end and is_b_end:
            if a == route_a[0]: route_a.reverse()
            if b == route_b[-1]: route_b.reverse()

            merged = route_a + route_b
            routes[route_id_a] = merged
            del routes[route_id_b]

    return list(routes.values())


def sweep_clustering(
        order_ids: List[str], orders_by_id: Dict[str, dict], warehouse_lat: float, warehouse_lon: float
) -> List[List[str]]:
    """Groups orders by their polar angle originating from the warehouse."""
    angles = []
    for oid in order_ids:
        order = orders_by_id[oid]
        angle = math.atan2(order["lat"] - warehouse_lat, order["lon"] - warehouse_lon)
        angles.append((angle, oid))

    # Sort strictly by polar angle
    angles.sort(key=lambda x: x[0])

    clusters = []
    current = []
    for _, oid in angles:
        current.append(oid)
        if len(current) == MAX_CLUSTER_SIZE:
            clusters.append(current)
            current = []
    if current:
        clusters.append(current)

    return clusters


def _centroid_dist(orders_by_id, cluster_ids, order) -> float:
    cx = sum(orders_by_id[o]["lat"] for o in cluster_ids) / len(cluster_ids)
    cy = sum(orders_by_id[o]["lon"] for o in cluster_ids) / len(cluster_ids)
    return math.hypot(order["lat"] - cx, order["lon"] - cy)


def repair_clusters(
        warehouse_lat: float,
        warehouse_lon: float,
        orders_by_id: Dict[str, dict],
        clusters: List[List[str]],
        tariffs: List[TransportTariff],
) -> List[List[str]]:
    # ... (Keep existing repair_clusters logic exactly as is) ...
    fixed = []
    orphans = []

    for cluster_ids in clusters:
        cluster_orders = [orders_by_id[oid] for oid in cluster_ids]
        sol = best_cluster_solution(warehouse_lat, warehouse_lon, cluster_orders, tariffs)
        if sol is not None:
            fixed.append(list(cluster_ids))
            continue

        remaining = list(cluster_ids)
        while len(remaining) > 1:
            cx = sum(orders_by_id[o]["lat"] for o in remaining) / len(remaining)
            cy = sum(orders_by_id[o]["lon"] for o in remaining) / len(remaining)
            worst = max(
                remaining,
                key=lambda oid: (
                    orders_by_id[oid]["mass_kg"],
                    math.hypot(orders_by_id[oid]["lat"] - cx, orders_by_id[oid]["lon"] - cy),
                ),
            )
            remaining.remove(worst)
            orphans.append(worst)
            sol = best_cluster_solution(
                warehouse_lat, warehouse_lon, [orders_by_id[o] for o in remaining], tariffs
            )
            if sol is not None:
                break
        if remaining:
            fixed.append(remaining)

    for oid in orphans:
        placed = False
        cand_order = sorted(
            range(len(fixed)),
            key=lambda idx: _centroid_dist(orders_by_id, fixed[idx], orders_by_id[oid]),
        )
        for idx in cand_order:
            if len(fixed[idx]) >= MAX_CLUSTER_SIZE:
                continue
            trial = fixed[idx] + [oid]
            sol = best_cluster_solution(
                warehouse_lat, warehouse_lon, [orders_by_id[o] for o in trial], tariffs
            )
            if sol is not None:
                fixed[idx] = trial
                placed = True
                break
        if not placed:
            fixed.append([oid])

    return fixed


def enforce_courier_capacity(
        warehouse_lat: float,
        warehouse_lon: float,
        orders_by_id: Dict[str, dict],
        clusters: List[List[str]],
        tariffs: List[TransportTariff],
        max_couriers: int,
) -> List[List[str]]:
    # ... (Keep existing enforce_courier_capacity logic exactly as is) ...
    clusters = [list(c) for c in clusters]
    sols = [
        best_cluster_solution(warehouse_lat, warehouse_lon,
                              [orders_by_id[o] for o in c], tariffs)
        for c in clusters
    ]
    assert all(s is not None for s in sols), "enforce_courier_capacity получила недопустимый кластер"

    while required_couriers(sols) > max_couriers:
        best_pair = None
        best_penalty = float("inf")
        best_merged_sol = None

        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                if len(clusters[i]) + len(clusters[j]) > MAX_CLUSTER_SIZE:
                    continue
                overlap = min(sols[i]["finish_at"], sols[j]["finish_at"]) - \
                          max(sols[i]["start_at"], sols[j]["start_at"])
                if overlap <= pd.Timedelta(0):
                    continue

                trial_ids = clusters[i] + clusters[j]
                trial_sol = best_cluster_solution(
                    warehouse_lat, warehouse_lon,
                    [orders_by_id[o] for o in trial_ids], tariffs,
                )
                if trial_sol is None:
                    continue

                penalty = trial_sol["cost"] - sols[i]["cost"] - sols[j]["cost"]
                if penalty < best_penalty:
                    best_penalty = penalty
                    best_pair = (i, j)
                    best_merged_sol = trial_sol

        if best_pair is None:
            break

        i, j = best_pair
        clusters[i] = clusters[i] + clusters[j]
        sols[i] = best_merged_sol
        del clusters[j]
        del sols[j]

    return clusters


def decode(
        model,
        data,
        orders_by_id: Dict[str, dict],
        warehouse_lat: float,
        warehouse_lon: float,
        tariffs: List[TransportTariff],
        max_couriers: Optional[int] = None,
        algorithm: str = "greedy",
        **algo_kwargs
) -> List[List[str]]:
    model.eval()
    with torch.no_grad():
        logits = model(data)
    probs = torch.sigmoid(logits)
    scores = (probs - 0.5).tolist()

    order_ids = data.order_ids
    ei = data.edge_index
    affinity = {}
    for k in range(ei.shape[1]):
        i, j = ei[0, k].item(), ei[1, k].item()
        oid_i, oid_j = order_ids[i], order_ids[j]
        key = tuple(sorted((oid_i, oid_j)))
        if key in affinity:
            affinity[key] = (affinity[key] + scores[k]) / 2
        else:
            affinity[key] = scores[k]

    # Algorithm Dispatcher
    if algorithm == "greedy":
        raw_clusters = greedy_correlation_clustering(order_ids, affinity)
    elif algorithm == "dbscan":
        raw_clusters = dbscan_clustering(order_ids, affinity, eps=algo_kwargs.get("eps", 0.5))
    elif algorithm == "clarke_wright":
        raw_clusters = clarke_wright_clustering(order_ids, affinity)
    elif algorithm == "sweep":
        raw_clusters = sweep_clustering(order_ids, orders_by_id, warehouse_lat, warehouse_lon)
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")

    fixed = repair_clusters(warehouse_lat, warehouse_lon, orders_by_id, raw_clusters, tariffs)
    if max_couriers is not None:
        fixed = enforce_courier_capacity(
            warehouse_lat, warehouse_lon, orders_by_id, fixed, tariffs, max_couriers
        )
    return fixed