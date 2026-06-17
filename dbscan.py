"""
dbscan_seeding.py

Seeds the evolutionary algorithm's initial population with DBSCAN-based
clusterings instead of pure random individuals, per clustering_task.pdf:

  orders: List[Order], warehouses: List[Warehouse], constraints: Constraint
    -> clusterizations: Set[Set[Trip]]

Pipeline:
  1. Load orders / warehouses / transport_types for one task (polygon).
  2. external_distance_metric: travel-time estimate between two points for a
     given transport type. PLACEHOLDER — the task brief explicitly calls for
     this to be its own service (e.g. a self-hosted OSRM/Valhalla instance,
     or a vendor routing API). Swap build_distance_matrix's call site to hit
     that service instead of haversine_m once it exists.
  3. generalized_distance_metric: external_distance_metric + a penalty for
     incompatible pickup/deadline windows, so DBSCAN doesn't group orders
     that are close in space but impossible to serve on a single trip.
  4. Run DBSCAN per warehouse (a cluster is always scoped to one warehouse)
     across a grid of (transport, eps, min_samples) to get several distinct
     base partitions.
  5. Repair: DBSCAN noise (-1) is illegal in this domain (no unclustered
     orders allowed) and clusters may violate max_order_count / max_weight.
     merge_noise() and split_oversized() fix both.
  6. Assign each repaired cluster a feasible transport_type -> Trip.
  7. Recombine per-warehouse options into many full Clusterizations
     (a Clusterization = a Trip set that covers every order exactly once)
     to hand to the EA as seeded individuals.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, FrozenSet, List, Tuple

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, KMeans


# ---------------------------------------------------------------------------
# 1. Data model
# ---------------------------------------------------------------------------

@dataclass
class Order:
    order_id: int
    warehouse_id: int
    lat: float
    lon: float
    pickup_ready_at: datetime
    deadline_at: datetime
    weight_kg: float


@dataclass
class Warehouse:
    warehouse_id: int
    lat: float
    lon: float


@dataclass
class TransportType:
    code: str
    speed_kmh: float
    max_payload_kg: float


@dataclass
class Constraint:
    max_order_count: int
    max_weight_kg: float


@dataclass
class Trip:
    warehouse_id: int
    transport_type: str
    order_ids: FrozenSet[int]


Clusterization = List[Trip]  # one candidate solution: covers every order exactly once


# ---------------------------------------------------------------------------
# 2. Loading
# ---------------------------------------------------------------------------

def load_task(task_id: int, data_dir: str = ".") -> Tuple[List[Order], List[Warehouse], List[TransportType]]:
    orders_df = pd.read_csv(f"{data_dir}/orders.csv")
    wh_df = pd.read_csv(f"{data_dir}/warehouses.csv")
    tt_df = pd.read_csv(f"{data_dir}/transport_types.csv")

    orders_df = orders_df[orders_df.task_id == task_id]
    wh_df = wh_df[wh_df.task_id == task_id]

    orders = [
        Order(
            order_id=r.order_id,
            warehouse_id=r.warehouse_id,
            lat=r.order_lat,
            lon=r.order_lon,
            pickup_ready_at=pd.to_datetime(r.pickup_ready_at),
            deadline_at=pd.to_datetime(r.delivery_deadline_at),
            weight_kg=r.total_mass_kg,
        )
        for r in orders_df.itertuples()
    ]
    warehouses = [Warehouse(r.warehouse_id, r.lat, r.lon) for r in wh_df.itertuples()]
    transport_types = [TransportType(r.code, r.approx_speed_kmh, r.max_payload_kg) for r in tt_df.itertuples()]
    return orders, warehouses, transport_types


# ---------------------------------------------------------------------------
# 3. Distance metrics
# ---------------------------------------------------------------------------

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


ROAD_FACTOR = 1.35  # straight-line underestimates real street distance; replace with real router output


def external_distance_metric(o1: Order, o2: Order, transport: TransportType) -> float:
    """Estimated travel time in seconds between two points for a transport type.
    PLACEHOLDER for the real routing service called out in the task brief."""
    dist_m = haversine_m(o1.lat, o1.lon, o2.lat, o2.lon) * ROAD_FACTOR
    speed_m_s = transport.speed_kmh * 1000 / 3600
    return dist_m / speed_m_s


def time_window_penalty(o1: Order, o2: Order) -> float:
    """0 seconds if the two orders' [pickup_ready, deadline] windows overlap;
    otherwise the size of the gap between them, in seconds."""
    latest_start = max(o1.pickup_ready_at, o2.pickup_ready_at)
    earliest_end = min(o1.deadline_at, o2.deadline_at)
    gap = (latest_start - earliest_end).total_seconds()
    return max(0.0, gap)


TIME_PENALTY_WEIGHT = 0.5  # tune empirically against real route durations


def generalized_distance_metric(o1: Order, o2: Order, transport: TransportType) -> float:
    return external_distance_metric(o1, o2, transport) + TIME_PENALTY_WEIGHT * time_window_penalty(o1, o2)


def build_distance_matrix(orders: List[Order], transport: TransportType) -> np.ndarray:
    n = len(orders)
    mat = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = generalized_distance_metric(orders[i], orders[j], transport)
            mat[i, j] = mat[j, i] = d
    return mat


# ---------------------------------------------------------------------------
# 4. DBSCAN per warehouse
# ---------------------------------------------------------------------------

def dbscan_partition(orders: List[Order], transport: TransportType, eps: float, min_samples: int) -> Dict[int, List[int]]:
    """{cluster_label: [order_index, ...]}; label -1 is DBSCAN noise."""
    if len(orders) == 1:
        return {0: [0]}
    dmat = build_distance_matrix(orders, transport)
    labels = DBSCAN(eps=eps, min_samples=min_samples, metric="precomputed").fit_predict(dmat)
    clusters: Dict[int, List[int]] = {}
    for idx, lab in enumerate(labels):
        clusters.setdefault(int(lab), []).append(idx)
    return clusters


def eps_grid(orders: List[Order], transport: TransportType, n: int = 4) -> List[float]:
    """Eps candidates taken from the empirical distance distribution instead
    of a blind guess — robust across very different warehouse densities."""
    if len(orders) < 2:
        return [1.0]
    dmat = build_distance_matrix(orders, transport)
    upper = dmat[np.triu_indices_from(dmat, k=1)]
    pct = np.percentile(upper, [20, 40, 60, 80][:n])
    return sorted(set(float(p) for p in pct if p > 0))


# ---------------------------------------------------------------------------
# 5. Repair: zero noise, respect constraints
# ---------------------------------------------------------------------------

def cluster_weight(orders: List[Order], idxs: List[int]) -> float:
    return sum(orders[i].weight_kg for i in idxs)


def merge_noise(
        orders: List[Order], transport: TransportType, clusters: Dict[int, List[int]], constraint: Constraint
) -> Dict[int, List[int]]:
    """Every order must end up in some cluster. Fold DBSCAN noise into the
    nearest real cluster if it still respects the constraints; otherwise the
    order becomes its own singleton cluster (never dropped)."""
    if -1 not in clusters:
        return clusters
    noise = clusters.pop(-1)
    next_label = max(clusters.keys(), default=-1) + 1
    for idx in noise:
        best_label, best_d = None, math.inf
        for lab, members in clusters.items():
            if len(members) + 1 > constraint.max_order_count:
                continue
            if cluster_weight(orders, members) + orders[idx].weight_kg > constraint.max_weight_kg:
                continue
            d = min(generalized_distance_metric(orders[idx], orders[m], transport) for m in members)
            if d < best_d:
                best_d, best_label = d, lab
        if best_label is not None:
            clusters[best_label].append(idx)
        else:
            clusters[next_label] = [idx]
            next_label += 1
    return clusters


def split_oversized(
        orders: List[Order], clusters: Dict[int, List[int]], constraint: Constraint
) -> Dict[int, List[int]]:
    """Recursively bisect (by lat/lon KMeans) any cluster that breaks
    max_order_count or max_weight."""
    result: Dict[int, List[int]] = {}
    next_label = 0
    stack = list(clusters.values())
    while stack:
        members = stack.pop()
        too_many = len(members) > constraint.max_order_count
        too_heavy = cluster_weight(orders, members) > constraint.max_weight_kg
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
# 6. Transport-type assignment -> Trips
# ---------------------------------------------------------------------------

def feasible_transports(
        orders: List[Order], idxs: List[int], transport_types: List[TransportType], constraint: Constraint
) -> List[TransportType]:
    w = cluster_weight(orders, idxs)
    return [t for t in transport_types if w <= t.max_payload_kg and len(idxs) <= constraint.max_order_count]


def clusters_to_trips(
        orders: List[Order],
        warehouse_id: int,
        clusters: Dict[int, List[int]],
        transport_types: List[TransportType],
        constraint: Constraint,
        rng: np.random.Generator,
) -> List[Trip]:
    trips = []
    for members in clusters.values():
        choices = feasible_transports(orders, members, transport_types, constraint)
        if not choices:
            # No single transport type can take the whole cluster: fall back
            # to singletons on the smallest-payload vehicle rather than
            # silently dropping orders.
            fallback = min(transport_types, key=lambda tt: tt.max_payload_kg)
            for m in members:
                trips.append(Trip(warehouse_id, fallback.code, frozenset([orders[m].order_id])))
            continue
        t = choices[rng.integers(len(choices))]
        trips.append(Trip(warehouse_id, t.code, frozenset(orders[m].order_id for m in members)))
    return trips


# ---------------------------------------------------------------------------
# 7. Assemble many DBSCAN-seeded individuals for the EA
# ---------------------------------------------------------------------------

def seed_population(
        orders: List[Order],
        transport_types: List[TransportType],
        constraint: Constraint,
        n_individuals: int = 2000,
        seed: int = 0,
) -> List[Clusterization]:
    rng = np.random.default_rng(seed)
    by_wh: Dict[int, List[Order]] = {}
    for o in orders:
        by_wh.setdefault(o.warehouse_id, []).append(o)

    # Per warehouse, precompute several repaired DBSCAN partitions across a
    # grid of (transport, eps, min_samples). Using each transport's own speed
    # as the metric's time scale (not just one reference vehicle) is what
    # gives genuinely different — not just noisy — partitions.
    per_wh_options: Dict[int, List[Dict[int, List[int]]]] = {}
    for wh_id, wh_orders in by_wh.items():
        options = []
        for transport in transport_types:
            for eps in eps_grid(wh_orders, transport):
                for min_samples in (1, 2, 3):
                    raw = dbscan_partition(wh_orders, transport, eps, min_samples)
                    repaired = merge_noise(wh_orders, transport, dict(raw), constraint)
                    repaired = split_oversized(wh_orders, repaired, constraint)
                    options.append(repaired)
        per_wh_options[wh_id] = options

    wh_ids = list(by_wh.keys())
    population: List[Clusterization] = []
    seen_signatures = set()
    attempts = 0
    while len(population) < n_individuals and attempts < n_individuals * 30:
        attempts += 1
        individual: Clusterization = []
        for wh_id in wh_ids:
            opts = per_wh_options[wh_id]
            clusters = opts[rng.integers(len(opts))]
            trips = clusters_to_trips(by_wh[wh_id], wh_id, clusters, transport_types, constraint, rng)
            individual.extend(trips)
        signature = frozenset((t.warehouse_id, t.transport_type, t.order_ids) for t in individual)
        if signature in seen_signatures:
            continue  # keep the population free of exact duplicates
        seen_signatures.add(signature)
        population.append(individual)
    return population


def validate_clusterization(individual: Clusterization, orders: List[Order]) -> None:
    """Sanity check matching the brief: every order in exactly one trip, no noise."""
    seen = []
    for trip in individual:
        seen.extend(trip.order_ids)
    expected = sorted(o.order_id for o in orders)
    assert sorted(seen) == expected, f"coverage mismatch: {sorted(seen)} vs {expected}"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    DATA_DIR = "data"
    orders, warehouses, transport_types = load_task(1, DATA_DIR)

    constraint = Constraint(
        max_order_count=5,                                       # placeholder: plug in real Constraint values
        max_weight_kg=max(t.max_payload_kg for t in transport_types),
    )

    population = seed_population(orders, transport_types, constraint, n_individuals=2000, seed=42)

    print(f"Orders: {len(orders)}, warehouses: {len(warehouses)}, transport types: {[t.code for t in transport_types]}")
    print(f"Distinct DBSCAN-seeded individuals generated: {len(population)}")

    for ind in population[:3]:
        validate_clusterization(ind, orders)
    print("Coverage check passed on sample individuals (every order assigned exactly once, no noise).")

    print("\nSample individual:")
    for trip in population[0]:
        print(f"  warehouse={trip.warehouse_id} transport={trip.transport_type} orders={sorted(trip.order_ids)}")

    trip_counts = [len(ind) for ind in population]
    print(f"\nTrip-count range across the seeded population: {min(trip_counts)}-{max(trip_counts)}")