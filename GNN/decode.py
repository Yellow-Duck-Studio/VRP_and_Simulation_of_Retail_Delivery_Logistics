"""Affinity-логиты по рёбрам -> валидное разбиение заказов на кластеры."""

import math
from typing import Dict, List, Optional

import pandas as pd
import torch

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


def enforce_courier_capacity(
    warehouse_lat: float,
    warehouse_lon: float,
    orders_by_id: Dict[str, dict],
    clusters: List[List[str]],
    tariffs: List[TransportTariff],
    max_couriers: int,
) -> List[List[str]]:
    """
    Жадно сливает кластеры, пока набор рейсов не станет исполнимым штатом
    в max_couriers курьеров (required_couriers(...) <= max_couriers).
    На каждой итерации выбирает пару кластеров с максимальным пересечением
    по времени (это то, что реально создаёт потребность в доп. курьере) и
    минимальным приростом стоимости при слиянии, и объединяет их в один
    рейс — если объединение допустимо по MAX_CLUSTER_SIZE/грузоподъёмности/
    дедлайнам (проверяется через best_cluster_solution, как и везде в этом
    модуле).

    Если дальше сливать нечего (все допустимые слияния исчерпаны), но лимит
    всё ещё не соблюдён — возвращает то, что получилось, БЕЗ исключения.
    Это осознанное решение: в проде лучше вернуть "неидеальный, но
    рабочий" план и залогировать превышение штата, чем упасть или молча
    нарушить дедлайны. Вызывающий код (infer.py) должен проверить
    required_couriers() на результате и явно предупредить оператора, если
    лимит всё ещё превышен.
    """
    clusters = [list(c) for c in clusters]
    sols = [
        best_cluster_solution(warehouse_lat, warehouse_lon,
                               [orders_by_id[o] for o in c], tariffs)
        for c in clusters
    ]
    # Все кластеры сюда должны приходить уже допустимыми (после repair_clusters),
    # так что sols не должен содержать None. Если содержит — это баг выше по
    # пайплайну, а не то, что эта функция должна молча проглатывать.
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
                    continue  # не пересекаются по времени -> слияние тут не поможет со штатом

                trial_ids = clusters[i] + clusters[j]
                trial_sol = best_cluster_solution(
                    warehouse_lat, warehouse_lon,
                    [orders_by_id[o] for o in trial_ids], tariffs,
                )
                if trial_sol is None:
                    continue  # объединённый кластер недопустим (масса/дедлайны/размер)

                penalty = trial_sol["cost"] - sols[i]["cost"] - sols[j]["cost"]
                if penalty < best_penalty:
                    best_penalty = penalty
                    best_pair = (i, j)
                    best_merged_sol = trial_sol

        if best_pair is None:
            break  # больше нечего сливать — возвращаем как есть, см. docstring

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
    fixed = repair_clusters(warehouse_lat, warehouse_lon, orders_by_id, raw_clusters, tariffs)
    if max_couriers is not None:
        fixed = enforce_courier_capacity(
            warehouse_lat, warehouse_lon, orders_by_id, fixed, tariffs, max_couriers
        )
    return fixed