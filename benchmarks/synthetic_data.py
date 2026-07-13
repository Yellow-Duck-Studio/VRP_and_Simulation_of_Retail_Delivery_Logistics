"""
benchmarks/synthetic_data.py

Synthetic data generator for reproducibility & benchmarking.

Produces a single task with N explicitly separated geographic clusters
(default: "North" and "South") so that any reasonable clustering
algorithm (Sweep, DBSCAN, Clarke-Wright, ...) should trivially recover
the obvious split. This gives a fast, fully deterministic fixture for
benchmarking and for sanity-checking that an algorithm isn't doing
something pathological.

Design notes:
- Each cluster's orders are tightly jittered around a center point
  (small noise, e.g. ~1 km) while the cluster centers themselves are
  placed far apart (tens of km) -> the geographical separation is
  unambiguous.
- The generator uses its own `random.Random(seed)` instance instead of
  the global `random` module. This means calling
  `generate_synthetic_task(seed=42)` does NOT disturb the global RNG
  state, so the caller can deterministically `random.seed(42)` right
  before running an algorithm without any "leftover" randomness from
  data generation leaking into the algorithm's own random choices.
  
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

from evolutionary_algorithm.domain import Order


@dataclass(frozen=True)
class SyntheticGeoCluster:
    """One geographically-obvious blob of orders."""
    name: str
    center_lat: float
    center_lon: float
    n_orders: int
    jitter_deg: float = 0.01  # ~1.1 km of noise around the center


@dataclass(frozen=True)
class SyntheticDataset:
    task_id: str
    orders: List[Order]
    warehouses: Dict[int, Tuple[float, float]]
    clusters: Tuple[SyntheticGeoCluster, ...] = field(default_factory=tuple)


# Two clusters ~33km apart (0.30 deg latitude), each with ~1km internal
# jitter (0.01 deg). At this scale the separation between clusters is
# roughly 30x the internal spread of any single cluster - unambiguous
# for any density- or sweep-based method.
DEFAULT_CLUSTERS = (
    SyntheticGeoCluster(name="North", center_lat=55.85, center_lon=37.80, n_orders=15),
    SyntheticGeoCluster(name="South", center_lat=55.55, center_lon=37.80, n_orders=15),
)


def generate_synthetic_task(
    task_id: str = "synthetic_1",
    clusters: Tuple[SyntheticGeoCluster, ...] = DEFAULT_CLUSTERS,
    warehouse_id: int = 1,
    warehouse_lat: float = 55.70,
    warehouse_lon: float = 37.80,
    pickup_window_minutes: float = 10.0,
    delivery_window_minutes: float = 90.0,
    mass_range_kg: Tuple[float, float] = (0.5, 4.0),
    seed: int = 42,
) -> SyntheticDataset:
    """
    Builds a synthetic task with explicitly distinct geographical
    clusters of orders, all served from a single central warehouse.

    Deadlines are generated generously relative to the cluster
    distances/speeds in transport_types.csv so that a reasonable
    clustering produces mostly *valid* solutions - which is what you
    want for a benchmark whose point is to compare fitness quality,
    not to stress-test infeasibility handling.
    """
    rng = random.Random(seed)
    base_time = datetime(2026, 6, 7, 9, 0, 0, tzinfo=timezone(timedelta(hours=3)))

    orders: List[Order] = []
    order_id = 1
    for cluster in clusters:
        for _ in range(cluster.n_orders):
            lat = cluster.center_lat + rng.uniform(-cluster.jitter_deg, cluster.jitter_deg)
            lon = cluster.center_lon + rng.uniform(-cluster.jitter_deg, cluster.jitter_deg)

            pickup_ready_at = base_time + timedelta(
                minutes=rng.uniform(0, pickup_window_minutes)
            )
            delivery_deadline_at = pickup_ready_at + timedelta(
                minutes=rng.uniform(delivery_window_minutes * 0.6, delivery_window_minutes)
            )
            mass = rng.uniform(*mass_range_kg)

            orders.append(
                Order(
                    order_id=order_id,
                    warehouse_id=warehouse_id,
                    lat=lat,
                    lon=lon,
                    pickup_ready_at=pickup_ready_at,
                    delivery_deadline_at=delivery_deadline_at,
                    total_mass_kg=round(mass, 3),
                )
            )
            order_id += 1

    warehouses = {warehouse_id: (warehouse_lat, warehouse_lon)}

    return SyntheticDataset(task_id=task_id, orders=orders, warehouses=warehouses, clusters=clusters)


def dataset_to_csv_rows(dataset: SyntheticDataset) -> List[dict]:
    """
    Optional helper: flattens a SyntheticDataset into rows matching the
    real orders.csv schema, in case you want to dump it to disk and
    feed it through the normal `load_all_orders` path instead of
    passing Order objects directly in-process.

    Columns match ../data/small/orders.csv:
    task_id,order_id,warehouse_id,order_lat,order_lon,pickup_ready_at,
    created_at,delivery_deadline_at,total_mass_kg
    """
    rows = []
    for o in dataset.orders:
        created_at = o.pickup_ready_at - timedelta(minutes=8)
        rows.append({
            "task_id": dataset.task_id,
            "order_id": o.order_id,
            "warehouse_id": o.warehouse_id,
            "order_lat": o.lat,
            "order_lon": o.lon,
            "pickup_ready_at": o.pickup_ready_at.isoformat(),
            "created_at": created_at.isoformat(),
            "delivery_deadline_at": o.delivery_deadline_at.isoformat(),
            "total_mass_kg": o.total_mass_kg,
        })
    return rows
