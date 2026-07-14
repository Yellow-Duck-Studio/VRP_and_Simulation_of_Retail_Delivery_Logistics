"""Build dimensionless, logistics-aware graphs for GNN v2."""

from __future__ import annotations

import math
from statistics import median
from typing import Iterable

import pandas as pd
import torch
from torch_geometric.data import Data

from config_v2 import (
    DAY_SCALE_MIN,
    DISTANCE_SCALE_KM,
    EDGE_FEATURE_DIM,
    NODE_FEATURE_DIM,
    TIME_SCALE_MIN,
)
from costs import best_cluster_solution
from geo import haversine_km, to_local_km
from io_utils import TransportTariff, WarehouseInstance


def _minutes(delta) -> float:
    return delta.total_seconds() / 60.0


def _clip(value: float, low: float = -5.0, high: float = 5.0) -> float:
    return max(low, min(high, float(value)))


def _scaled(value: float, scale: float) -> float:
    return _clip(value / max(scale, 1e-6))


def _capacity_profile(tariffs: Iterable[TransportTariff]) -> tuple[float, float, float]:
    capacities = sorted(max(float(t.max_payload_kg), 1e-6) for t in tariffs)
    if not capacities:
        raise ValueError("At least one transport tariff is required")
    return capacities[0], float(median(capacities)), capacities[-1]


def _mass_ratios(mass: float, capacities: tuple[float, float, float]) -> list[float]:
    return [_clip(mass / capacity, 0.0, 5.0) for capacity in capacities]


def _window_iou(first: dict, second: dict) -> float:
    start = max(first["pickup_ready_at"], second["pickup_ready_at"])
    end = min(first["delivery_deadline_at"], second["delivery_deadline_at"])
    intersection = max(0.0, _minutes(end - start))
    union_start = min(first["pickup_ready_at"], second["pickup_ready_at"])
    union_end = max(first["delivery_deadline_at"], second["delivery_deadline_at"])
    union = max(0.0, _minutes(union_end - union_start))
    return intersection / union if union > 0 else 0.0


def _sequence_slack(
    warehouse_lat: float,
    warehouse_lon: float,
    first: dict,
    second: dict,
    tariffs: list[TransportTariff],
) -> tuple[bool, float]:
    total_mass = first["mass_kg"] + second["mass_kg"]
    start_time = max(first["pickup_ready_at"], second["pickup_ready_at"])
    best_slack = float("-inf")

    for tariff in tariffs:
        if total_mass > tariff.max_payload_kg:
            continue
        first_leg = haversine_km(warehouse_lat, warehouse_lon, first["lat"], first["lon"])
        second_leg = haversine_km(first["lat"], first["lon"], second["lat"], second["lon"])
        first_arrival = start_time + pd.Timedelta(minutes=first_leg / tariff.approx_speed_kmh * 60.0)
        second_arrival = first_arrival + pd.Timedelta(minutes=second_leg / tariff.approx_speed_kmh * 60.0)
        route_slack = min(
            _minutes(first["delivery_deadline_at"] - first_arrival),
            _minutes(second["delivery_deadline_at"] - second_arrival),
        )
        best_slack = max(best_slack, route_slack)

    if best_slack == float("-inf"):
        return False, -TIME_SCALE_MIN * 5.0
    return best_slack >= 0.0, best_slack


def _single_order_context(
    order: dict,
    warehouse_lat: float,
    warehouse_lon: float,
    tariffs: list[TransportTariff],
) -> tuple[float, float, float, float]:
    feasible_tariffs = [t for t in tariffs if order["mass_kg"] <= t.max_payload_kg]
    if feasible_tariffs:
        fastest_speed = max(t.approx_speed_kmh for t in feasible_tariffs)
    else:
        fastest_speed = max(t.approx_speed_kmh for t in tariffs)

    distance = haversine_km(warehouse_lat, warehouse_lon, order["lat"], order["lon"])
    travel_min = distance / fastest_speed * 60.0
    slack_min = _minutes(order["delivery_deadline_at"] - order["pickup_ready_at"]) - travel_min
    solution = best_cluster_solution(warehouse_lat, warehouse_lon, [order], tariffs)
    cost_feature = math.log1p(max(solution["cost"], 0.0)) / 10.0 if solution else 0.0
    feasible_fraction = len(feasible_tariffs) / len(tariffs)
    return travel_min, slack_min, cost_feature, feasible_fraction


def build_graph_v2(inst: WarehouseInstance, tariffs: list[TransportTariff]) -> Data:
    orders = inst.orders
    n_orders = len(orders)
    if not tariffs:
        raise ValueError("At least one transport tariff is required")

    capacities = _capacity_profile(tariffs)
    min_pickup = min((o["pickup_ready_at"] for o in orders), default=pd.Timestamp(0))
    order_context = []
    node_features = []

    for order in orders:
        x_km, y_km = to_local_km(order["lat"], order["lon"], inst.warehouse_lat, inst.warehouse_lon)
        radial_km = math.hypot(x_km, y_km)
        angle = math.atan2(y_km, x_km)
        window_min = _minutes(order["delivery_deadline_at"] - order["pickup_ready_at"])
        pickup_offset = _minutes(order["pickup_ready_at"] - min_pickup)
        deadline_offset = _minutes(order["delivery_deadline_at"] - min_pickup)
        created_to_ready = _minutes(order["pickup_ready_at"] - order["created_at"])
        travel_min, slack_min, cost_feature, feasible_fraction = _single_order_context(
            order, inst.warehouse_lat, inst.warehouse_lon, tariffs
        )
        order_context.append((x_km, y_km, radial_km, cost_feature))
        node_features.append(
            [
                _scaled(x_km, DISTANCE_SCALE_KM),
                _scaled(y_km, DISTANCE_SCALE_KM),
                _scaled(radial_km, DISTANCE_SCALE_KM),
                math.sin(angle),
                math.cos(angle),
                *_mass_ratios(order["mass_kg"], capacities),
                _scaled(window_min, TIME_SCALE_MIN),
                _scaled(pickup_offset, DAY_SCALE_MIN),
                _scaled(deadline_offset, DAY_SCALE_MIN),
                _scaled(created_to_ready, TIME_SCALE_MIN),
                _scaled(travel_min, TIME_SCALE_MIN),
                _scaled(slack_min, TIME_SCALE_MIN),
                _clip(cost_feature, 0.0, 5.0),
                feasible_fraction,
                _clip(n_orders / 100.0, 0.0, 5.0),
            ]
        )

    edge_index: list[list[int]] = []
    edge_features: list[list[float]] = []
    labels: list[float] = []
    id_to_cluster: dict[str, int] = {}
    if inst.clusters is not None:
        for cluster_index, cluster in enumerate(inst.clusters):
            for order_id in cluster:
                normalized_order_id = str(order_id)
                if normalized_order_id in id_to_cluster:
                    raise ValueError(
                        f"Order {normalized_order_id} occurs in multiple reference clusters "
                        f"for task={inst.task_id}, warehouse={inst.warehouse_id}"
                    )
                id_to_cluster[normalized_order_id] = cluster_index
        graph_order_ids = {str(order["order_id"]) for order in orders}
        missing = graph_order_ids - set(id_to_cluster)
        unexpected = set(id_to_cluster) - graph_order_ids
        if missing or unexpected:
            raise ValueError(
                f"Reference partition mismatch for task={inst.task_id}, warehouse={inst.warehouse_id}: "
                f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
            )

    single_costs = [context[3] for context in order_context]
    for i, first in enumerate(orders):
        for j, second in enumerate(orders):
            if i == j:
                continue

            distance_ij = haversine_km(first["lat"], first["lon"], second["lat"], second["lon"])
            pickup_diff = abs(_minutes(first["pickup_ready_at"] - second["pickup_ready_at"]))
            deadline_diff = abs(_minutes(first["delivery_deadline_at"] - second["delivery_deadline_at"]))
            combined_mass = first["mass_kg"] + second["mass_kg"]
            radial_i, radial_j = order_context[i][2], order_context[j][2]
            denominator = max(radial_i * radial_j, 1e-6)
            direction_cosine = (
                order_context[i][0] * order_context[j][0] + order_context[i][1] * order_context[j][1]
            ) / denominator
            clarke_saving = radial_i + radial_j - distance_ij

            feasible_ij, slack_ij = _sequence_slack(
                inst.warehouse_lat, inst.warehouse_lon, first, second, tariffs
            )
            feasible_ji, slack_ji = _sequence_slack(
                inst.warehouse_lat, inst.warehouse_lon, second, first, tariffs
            )
            pair_solution = best_cluster_solution(
                inst.warehouse_lat, inst.warehouse_lon, [first, second], tariffs
            )
            separate_cost = math.expm1(single_costs[i] * 10.0) + math.expm1(single_costs[j] * 10.0)
            if pair_solution and separate_cost > 0:
                relative_cost_saving = (separate_cost - pair_solution["cost"]) / separate_cost
            else:
                relative_cost_saving = -1.0

            edge_index.append([i, j])
            edge_features.append(
                [
                    _scaled(distance_ij, DISTANCE_SCALE_KM),
                    _scaled(pickup_diff, TIME_SCALE_MIN),
                    _scaled(deadline_diff, TIME_SCALE_MIN),
                    *_mass_ratios(combined_mass, capacities),
                    _window_iou(first, second),
                    _scaled(clarke_saving, DISTANCE_SCALE_KM),
                    _clip(direction_cosine, -1.0, 1.0),
                    _scaled(abs(radial_i - radial_j), DISTANCE_SCALE_KM),
                    float(feasible_ij or feasible_ji),
                    float(feasible_ij and feasible_ji),
                    _scaled(max(slack_ij, slack_ji), TIME_SCALE_MIN),
                    float(pair_solution is not None),
                    _clip(relative_cost_saving, -1.0, 1.0),
                ]
            )

            if inst.clusters is not None:
                first_cluster = id_to_cluster.get(str(first["order_id"]), -1)
                second_cluster = id_to_cluster.get(str(second["order_id"]), -1)
                labels.append(float(first_cluster >= 0 and first_cluster == second_cluster))

    x = torch.tensor(node_features, dtype=torch.float32).reshape(n_orders, NODE_FEATURE_DIM)
    if edge_index:
        edge_index_tensor = torch.tensor(edge_index, dtype=torch.long).t().contiguous()
        edge_attr = torch.tensor(edge_features, dtype=torch.float32)
    else:
        edge_index_tensor = torch.empty((2, 0), dtype=torch.long)
        edge_attr = torch.empty((0, EDGE_FEATURE_DIM), dtype=torch.float32)

    graph = Data(x=x, edge_index=edge_index_tensor, edge_attr=edge_attr)
    graph.order_ids = [str(order["order_id"]) for order in orders]
    graph.task_id = str(inst.task_id)
    graph.warehouse_id = str(inst.warehouse_id)
    if inst.clusters is not None:
        graph.y = torch.tensor(labels, dtype=torch.float32)
    return graph


class WarehouseGraphDatasetV2(torch.utils.data.Dataset):
    def __init__(self, instances: list[WarehouseInstance], tariffs: list[TransportTariff]):
        self.instances = [instance for instance in instances if len(instance.orders) >= 2]
        self.graphs = [build_graph_v2(instance, tariffs) for instance in self.instances]

    def __len__(self) -> int:
        return len(self.graphs)

    def __getitem__(self, index: int) -> Data:
        return self.graphs[index]
