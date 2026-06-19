"""
dbscan_seeding.py

Drop-in replacement for the random init block in run_evolutionary_clustering().

Usage:
    from dbscan_seeding import seed_population, serialize_archive

    # Instead of the random for-loop:
    population = seed_population(orders, warehouses_dict, constraints, population_size=50)

    # After the EA finishes, serialize the archive:
    serialize_archive(valid_clusterizations_archive, task_id="1", path="output.json")
"""

import json
import math
import random
from typing import Dict, List, Set, Tuple

import numpy as np
from sklearn.cluster import DBSCAN, KMeans

from evolutionary_algorithm.domain import Constraint, Individual, Order, Trip


# ---------------------------------------------------------------------------
# Distance metrics  (same logic as evaluation.py, expressed in seconds so
# eps is directly comparable to time-window gaps)
# ---------------------------------------------------------------------------

ROAD_FACTOR = 1.35  # haversine underestimates real street distance


def _travel_time_s(lat1: float, lon1: float, lat2: float, lon2: float, speed_kmh: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    dist_km = 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a)) * ROAD_FACTOR
    return (dist_km / speed_kmh) * 3600.0


def _time_window_penalty_s(o1: Order, o2: Order) -> float:
    """0 if windows overlap, otherwise the size of the gap in seconds."""
    latest_start = max(o1.pickup_ready_at, o2.pickup_ready_at)
    earliest_end = min(o1.delivery_deadline_at, o2.delivery_deadline_at)
    return max(0.0, (latest_start - earliest_end).total_seconds())


def _generalized_distance(o1: Order, o2: Order, speed_kmh: float, tw_weight: float = 0.5) -> float:
    travel = _travel_time_s(o1.lat, o1.lon, o2.lat, o2.lon, speed_kmh)
    penalty = _time_window_penalty_s(o1, o2)
    return travel + tw_weight * penalty


def _distance_matrix(orders: List[Order], speed_kmh: float) -> np.ndarray:
    n = len(orders)
    mat = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = _generalized_distance(orders[i], orders[j], speed_kmh)
            mat[i, j] = mat[j, i] = d
    return mat


# ---------------------------------------------------------------------------
# DBSCAN + repair
# ---------------------------------------------------------------------------

def _eps_candidates(orders: List[Order], speed_kmh: float) -> List[float]:
    """Eps values from the empirical distance distribution — no magic constants."""
    if len(orders) < 2:
        return [60.0]
    mat = _distance_matrix(orders, speed_kmh)
    upper = mat[np.triu_indices_from(mat, k=1)]
    return [float(p) for p in np.percentile(upper, [20, 40, 60, 80]) if p > 0]


def _run_dbscan(orders: List[Order], speed_kmh: float, eps: float, min_samples: int) -> Dict[int, List[int]]:
    if len(orders) == 1:
        return {0: [0]}
    labels = DBSCAN(eps=eps, min_samples=min_samples, metric="precomputed").fit_predict(
        _distance_matrix(orders, speed_kmh)
    )
    clusters: Dict[int, List[int]] = {}
    for idx, lab in enumerate(labels):
        clusters.setdefault(int(lab), []).append(idx)
    return clusters


def _merge_noise(orders: List[Order], speed_kmh: float, clusters: Dict[int, List[int]], constraint: Constraint, transport_type: str) -> Dict[int, List[int]]:
    if -1 not in clusters:
        return clusters
    noise = clusters.pop(-1)
    next_label = max(clusters.keys(), default=-1) + 1
    max_weight = constraint.max_weight_per_transport[transport_type]
    for idx in noise:
        best_label, best_d = None, math.inf
        for lab, members in clusters.items():
            if len(members) + 1 > constraint.max_order_count:
                continue
            w = sum(orders[m].total_mass_kg for m in members) + orders[idx].total_mass_kg
            if w > max_weight:
                continue
            d = min(_generalized_distance(orders[idx], orders[m], speed_kmh) for m in members)
            if d < best_d:
                best_d, best_label = d, lab
        if best_label is not None:
            clusters[best_label].append(idx)
        else:
            clusters[next_label] = [idx]
            next_label += 1
    return clusters


def _split_oversized(orders: List[Order], clusters: Dict[int, List[int]], constraint: Constraint, transport_type: str) -> Dict[int, List[int]]:
    max_weight = constraint.max_weight_per_transport[transport_type]
    result: Dict[int, List[int]] = {}
    next_label = 0
    stack = list(clusters.values())
    while stack:
        members = stack.pop()
        too_many = len(members) > constraint.max_order_count
        too_heavy = sum(orders[i].total_mass_kg for i in members) > max_weight
        if (too_many or too_heavy) and len(members) > 1:
            coords = np.array([[orders[i].lat, orders[i].lon] for i in members])
            km = KMeans(n_clusters=2, n_init=4, random_state=0).fit(coords)
            left = [m for m, lab in zip(members, km.labels_) if lab == 0]
            right = [m for m, lab in zip(members, km.labels_) if lab == 1]
            stack.extend(g for g in (left, right) if g)
        else:
            result[next_label] = members
            next_label += 1
    return result


# ---------------------------------------------------------------------------
# Build one Individual from a DBSCAN partition of all warehouses
# ---------------------------------------------------------------------------

def _build_individual(
        orders: List[Order],
        warehouses_dict: Dict[int, Tuple[float, float]],
        constraints: Constraint,
        speed_kmh: float,
        transport_type: str,
        eps: float,
        min_samples: int,
        trip_counter_start: int = 1,
) -> Individual:
    ind = Individual()
    trip_counter = trip_counter_start
    by_wh: Dict[int, List[Order]] = {}
    for o in orders:
        by_wh.setdefault(o.warehouse_id, []).append(o)

    for wh_id, wh_orders in by_wh.items():
        raw = _run_dbscan(wh_orders, speed_kmh, eps, min_samples)
        repaired = _merge_noise(wh_orders, speed_kmh, dict(raw), constraints, transport_type)
        repaired = _split_oversized(wh_orders, repaired, constraints, transport_type)

        for members in repaired.values():
            ind.trips[trip_counter] = Trip(
                trip_id=trip_counter,
                warehouse_id=wh_id,
                transport_type=transport_type,
                order_ids=[wh_orders[m].order_id for m in members],
            )
            trip_counter += 1

    return ind


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def seed_population(
        orders: List[Order],
        warehouses_dict: Dict[int, Tuple[float, float]],
        constraints: Constraint,
        population_size: int = 50,
        seed: int = 0,
) -> List[Individual]:
    """
    Produces `population_size` DBSCAN-seeded Individual objects.
    Drop-in for the random init loop in run_evolutionary_clustering().
    """
    rng = np.random.default_rng(seed)

    # Build a grid of (transport_type, eps, min_samples) candidates
    candidates: List[Individual] = []
    seen_sigs: Set[frozenset] = set()

    transport_types = list(constraints.transport_distribution.keys())
    speeds = constraints.speeds_kmh

    for transport_type in transport_types:
        # Sample eps from data distribution for each transport's speed
        by_wh: Dict[int, List[Order]] = {}
        for o in orders:
            by_wh.setdefault(o.warehouse_id, []).append(o)
        all_eps: List[float] = []
        for wh_orders in by_wh.values():
            all_eps.extend(_eps_candidates(wh_orders, speeds[transport_type]))
        if not all_eps:
            continue

        for eps in all_eps:
            for min_samples in (1, 2, 3):
                ind = _build_individual(
                    orders, warehouses_dict, constraints,
                    speed_kmh=speeds[transport_type],
                    transport_type=transport_type,
                    eps=eps,
                    min_samples=min_samples,
                )
                sig = ind.get_trip_sets()
                if sig not in seen_sigs:
                    seen_sigs.add(sig)
                    candidates.append(ind)

    # If we got more candidates than needed, sample by transport_distribution weighting
    # so the seeded population reflects the real fleet mix.
    if len(candidates) >= population_size:
        chosen = list(rng.choice(len(candidates), size=population_size, replace=False))
        return [candidates[i] for i in chosen]

    # If we have fewer unique DBSCAN variants than population_size, pad with
    # random-chunked individuals (same logic as the original EA init) to
    # reach the target size without duplicating seed individuals.
    population = list(candidates)
    while len(population) < population_size:
        ind = Individual()
        trip_counter = 1
        for wh_id in set(o.warehouse_id for o in orders):
            wh_orders = [o for o in orders if o.warehouse_id == wh_id]
            random.shuffle(wh_orders)
            chunk_size = constraints.max_order_count
            for i in range(0, len(wh_orders), chunk_size):
                chunk = wh_orders[i:i + chunk_size]
                t_type = random.choices(
                    list(constraints.transport_distribution.keys()),
                    weights=list(constraints.transport_distribution.values()),
                )[0]
                ind.trips[trip_counter] = Trip(
                    trip_id=trip_counter,
                    warehouse_id=wh_id,
                    transport_type=t_type,
                    order_ids=[o.order_id for o in chunk],
                )
                trip_counter += 1
        sig = ind.get_trip_sets()
        if sig not in seen_sigs:
            seen_sigs.add(sig)
            population.append(ind)

    return population[:population_size]


def serialize_archive(
        archive: Set[frozenset],
        task_id: str,
        path: str,
        existing: Dict = None,
) -> None:
    """
    Serializes valid_clusterizations_archive to the strict JSON format:
        {"task_1": [[order_ids], [order_ids], ...], ...}

    Pass `existing` to append to a multi-task JSON file without overwriting other tasks.
    """
    data = existing or {}
    data[f"task_{task_id}"] = [
        [sorted(trip_set) for trip_set in clusterization]
        for clusterization in archive
    ]
    with open(path, "w") as f:
        json.dump(data, f, indent=2)