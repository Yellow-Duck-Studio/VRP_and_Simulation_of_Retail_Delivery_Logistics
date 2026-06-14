"""
Clustering Task — Data Structures & External Distance Service
=============================================================
Matches the task specification:
  Input:  List[Order], List[Warehouse], Constraint
  Output: Set[Set[Trip]]  (clusterizations)

External distance metric is implemented as a straight-line Haversine
approximation.  Swap `HaversineDistanceService` for an OSRM/GraphHopper
client when a real routing engine is available.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set, Tuple
import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
# Core domain types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LatLon:
    lat: float
    lon: float


@dataclass
class Order:
    order_id: int
    warehouse_id: int
    location: LatLon
    pickup_ready_at: int      # Unix timestamp (seconds, UTC)
    deadline_at: int          # Unix timestamp (seconds, UTC)
    weight_kg: float
    task_id: Optional[int] = None

    @property
    def time_window_sec(self) -> int:
        return self.deadline_at - self.pickup_ready_at


@dataclass
class Warehouse:
    warehouse_id: int
    location: LatLon
    task_id: Optional[int] = None


@dataclass
class TransportType:
    code: str                   # 'walking' | 'moped' | 'car'
    approx_speed_kmh: float
    max_payload_kg: float

    # fee structure (from couriers table)
    per_km_fee: float = 0.0
    per_order_fee: float = 0.0


@dataclass
class Courier:
    courier_id: int
    transport: TransportType
    warehouse_travel_sec: Dict[int, int] = field(default_factory=dict)
    # warehouse_travel_sec[warehouse_id] = estimated seconds to reach warehouse


@dataclass
class Constraint:
    max_order_count: int         # max orders per trip
    max_weight_kg: float         # max total payload per trip (per transport)
    transport_distribution: Dict[str, float] = field(default_factory=dict)
    # e.g. {'car': 0.80, 'moped': 0.15, 'walking': 0.05}


# ──────────────────────────────────────────────────────────────────────────────
# Cluster / Trip types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Cluster:
    warehouse_id: int
    order_ids: List[int]

    @property
    def total_orders(self) -> int:
        return len(self.order_ids)

    def total_weight(self, order_map: Dict[int, Order]) -> float:
        return sum(order_map[oid].weight_kg for oid in self.order_ids)


@dataclass
class Trip:
    cluster: Cluster
    transport_type: TransportType

    def is_valid(self, constraint: Constraint, order_map: Dict[int, Order]) -> bool:
        if self.cluster.total_orders > constraint.max_order_count:
            return False
        if self.cluster.total_weight(order_map) > self.transport_type.max_payload_kg:
            return False
        return True


# A clusterization is a frozenset of frozen trip identifiers
# (represented here as a list of Trip objects for usability)
Clusterization = List[Trip]


# ──────────────────────────────────────────────────────────────────────────────
# External distance metric (required by spec)
# ──────────────────────────────────────────────────────────────────────────────

class HaversineDistanceService:
    """
    Implements external_distance_metric as straight-line Haversine distance
    in seconds, given a transport speed.

    Replace or extend with OSRM/GraphHopper for real road-network times.
    """

    @staticmethod
    def distance_km(a: LatLon, b: LatLon) -> float:
        R = 6371.0
        la1, lo1, la2, lo2 = map(radians, [a.lat, a.lon, b.lat, b.lon])
        dlat, dlon = la2 - la1, lo2 - lo1
        h = sin(dlat / 2) ** 2 + cos(la1) * cos(la2) * sin(dlon / 2) ** 2
        return 2 * R * asin(sqrt(h))

    def travel_time_sec(self, a: LatLon, b: LatLon, speed_kmh: float) -> int:
        """external_distance_metric(a, b) -> seconds"""
        return int((self.distance_km(a, b) / speed_kmh) * 3600)

    def matrix(
        self,
        points: List[LatLon],
        speed_kmh: float
    ) -> List[List[int]]:
        """Full N×N travel-time matrix in seconds."""
        n = len(points)
        return [
            [self.travel_time_sec(points[i], points[j], speed_kmh) for j in range(n)]
            for i in range(n)
        ]


def build_warehouse_distance_matrix(
    orders: List[Order],
    warehouse_id: int,
    dist_service: Optional[HaversineDistanceService] = None,
) -> Tuple[List[int], List[List[float]]]:
    """
    Returns (order_ids, matrix) — an N x N km distance matrix for all orders
    belonging to `warehouse_id`. Since clusters are warehouse-bound, this is
    the relevant unit of work for DBSCAN / Clark-Wright / GA encodings,
    rather than a full task-wide matrix (which mixes unrelated warehouses).
    """
    if dist_service is None:
        dist_service = HaversineDistanceService()

    wh_orders = [o for o in orders if o.warehouse_id == warehouse_id]
    ids = [o.order_id for o in wh_orders]
    n = len(wh_orders)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            matrix[i][j] = dist_service.distance_km(wh_orders[i].location, wh_orders[j].location)
    return ids, matrix


def generalized_distance_metric(
    a: LatLon,
    b: LatLon,
    transport: TransportType,
    dist_service: HaversineDistanceService,
    pickup_gap_sec: int = 0,
    weight_penalty_factor: float = 0.0,
) -> float:
    """
    generalized_distance_metric combines:
      - external_distance_metric (travel time in seconds)
      - pickup_gap_sec: wait at pickup before order is ready
      - weight_penalty_factor: optional penalty for heavier loads
    Returns an effective cost in seconds.
    """
    travel = dist_service.travel_time_sec(a, b, transport.approx_speed_kmh)
    return travel + pickup_gap_sec + weight_penalty_factor


# ──────────────────────────────────────────────────────────────────────────────
# Data loader — reads the prepared CSV outputs
# ──────────────────────────────────────────────────────────────────────────────

# Transport-type name mapping: raw CSV codes → spec names
_TYPE_MAP = {"bike": "moped", "foot": "walking", "car": "car"}

def load_transport_types(path: str) -> Dict[str, TransportType]:
    df = pd.read_csv(path)
    result = {}
    for _, row in df.iterrows():
        norm = _TYPE_MAP.get(row["code"], row["code"])
        result[norm] = TransportType(
            code=norm,
            approx_speed_kmh=float(row["approx_speed_kmh"]),
            max_payload_kg=float(row["max_payload_kg"]),
        )
    return result


def load_couriers(
    couriers_path: str,
    wte_path: str,
    transport_types: Dict[str, TransportType],
    task_id: int,
) -> List[Courier]:
    couriers_df = pd.read_csv(couriers_path)
    wte_df = pd.read_csv(wte_path)

    task_couriers = couriers_df[couriers_df["task_id"] == task_id]
    task_wte = wte_df[wte_df["task_id"] == task_id]

    couriers = []
    for _, row in task_couriers.iterrows():
        norm_type = _TYPE_MAP.get(row["transport_type"], row["transport_type"])
        tt = transport_types[norm_type]
        tt_with_fees = TransportType(
            code=tt.code,
            approx_speed_kmh=tt.approx_speed_kmh,
            max_payload_kg=tt.max_payload_kg,
            per_km_fee=float(row["per_km_fee"]),
            per_order_fee=float(row["per_order_fee"]),
        )
        wte_rows = task_wte[task_wte["courier_id"] == row["courier_id"]]
        wh_travel = dict(
            zip(
                wte_rows["warehouse_id"].tolist(),
                wte_rows["estimated_duration_sec"].tolist(),
            )
        )
        couriers.append(
            Courier(
                courier_id=int(row["courier_id"]),
                transport=tt_with_fees,
                warehouse_travel_sec=wh_travel,
            )
        )
    return couriers


def load_orders(path: str, task_id: int) -> List[Order]:
    df = pd.read_csv(path, parse_dates=["pickup_ready_at", "created_at", "delivery_deadline_at"])
    df = df[df["task_id"] == task_id]
    orders = []
    for _, row in df.iterrows():
        orders.append(
            Order(
                order_id=int(row["order_id"]),
                warehouse_id=int(row["warehouse_id"]),
                location=LatLon(lat=row["order_lat"], lon=row["order_lon"]),
                pickup_ready_at=int(pd.Timestamp(row["pickup_ready_at"]).timestamp()),
                deadline_at=int(pd.Timestamp(row["delivery_deadline_at"]).timestamp()),
                weight_kg=float(row["total_mass_kg"]),
                task_id=task_id,
            )
        )
    return orders


def load_warehouses(path: str, task_id: int) -> List[Warehouse]:
    df = pd.read_csv(path)
    df = df[df["task_id"] == task_id]
    return [
        Warehouse(
            warehouse_id=int(row["warehouse_id"]),
            location=LatLon(lat=row["lat"], lon=row["lon"]),
            task_id=task_id,
        )
        for _, row in df.iterrows()
    ]


def load_task(
    task_id: int,
    data_dir: str = "/mnt/user-data/outputs",
    constraint: Optional[Constraint] = None,
) -> Tuple[List[Order], List[Warehouse], List[Courier], Constraint]:
    """
    Convenience loader — returns (orders, warehouses, couriers, constraint)
    ready to pass to any clustering algorithm.
    """
    transport_types = load_transport_types(f"{data_dir}/transport_types.csv")
    orders      = load_orders(f"{data_dir}/orders.csv", task_id)
    warehouses  = load_warehouses(f"{data_dir}/warehouses.csv", task_id)
    couriers    = load_couriers(
        f"{data_dir}/couriers.csv",
        f"{data_dir}/warehouse_time_estimates.csv",
        transport_types,
        task_id,
    )
    if constraint is None:
        # Sensible defaults — tune per algorithm run
        constraint = Constraint(
            max_order_count=5,
            max_weight_kg=10.0,  # most restrictive (walking/moped)
            transport_distribution={"car": 0.33, "moped": 0.33, "walking": 0.34},
        )
    return orders, warehouses, couriers, constraint


# ──────────────────────────────────────────────────────────────────────────────
# Quick smoke test
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    dist_svc = HaversineDistanceService()

    for task_id in range(1, 11):
        orders, warehouses, couriers, constraint = load_task(task_id)
        order_map = {o.order_id: o for o in orders}

        n_walk = sum(1 for c in couriers if c.transport.code == "walking")
        n_moped = sum(1 for c in couriers if c.transport.code == "moped")
        n_car = sum(1 for c in couriers if c.transport.code == "car")

        print(f"Task {task_id:2d}: {len(orders):3d} orders, "
              f"{len(warehouses)} warehouses, "
              f"{len(couriers):3d} couriers "
              f"(walk {n_walk}, moped {n_moped}, car {n_car})")

        # Per-warehouse distance matrix sanity check
        for wh in warehouses:
            ids, mat = build_warehouse_distance_matrix(orders, wh.warehouse_id, dist_svc)
            n = len(ids)
            avg = sum(mat[i][j] for i in range(n) for j in range(n) if i != j) / (n * (n - 1))
            print(f"    warehouse {wh.warehouse_id}: {n} orders, "
                  f"avg pairwise dist {avg:.2f} km")
