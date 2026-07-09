"""Affinity-логиты по рёбрам -> валидное разбиение заказов на кластеры."""

import math
from typing import Dict, List

import torch

from config import MAX_CLUSTER_SIZE
from costs import best_cluster_solution
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


def decode(
    model,
    data,
    orders_by_id: Dict[str, dict],
    warehouse_lat: float,
    warehouse_lon: float,
    tariffs: List[TransportTariff],
) -> List[List[str]]:
    model.eval()
    with torch.no_grad():
        logits = model(data)
    probs = torch.sigmoid(logits)
    scores = (probs - 0.5).tolist()

    order_ids = data.order_ids  # список str
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

    raw_clusters = greedy_correlation_clustering(order_ids, affinity)
    return repair_clusters(warehouse_lat, warehouse_lon, orders_by_id, raw_clusters, tariffs)
