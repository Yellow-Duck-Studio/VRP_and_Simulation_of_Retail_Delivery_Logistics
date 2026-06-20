from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable
import math

from heuristics.core_utils import haversine_distance
from pipeline.types import OrderData, Solution, TaskContext


DEFAULT_FITNESS_CONFIG = {
    "capacity_penalty_weight": 1000.0,
    "mass_penalty_weight": 500.0,
    "sla_penalty_weight": 100.0,
    "sync_weight": 50.0,
    "fleet_weight": 2.0,
    "direction_weight": 5.0,
    "route_ordering": "deadline",
}


@dataclass(frozen=True)
class FitnessComponents:
    is_valid: bool
    t_total_hours: float
    p_hard: float
    p_capacity: float
    p_mass: float
    p_sla: float
    p_sync: float
    p_fleet: float
    p_direction: float
    total_distance_km: float
    late_orders_count: int
    total_lateness_minutes: float
    max_lateness_minutes: float
    total_orders: int
    trip_count: int
    avg_orders_per_trip: float

    @property
    def fitness_score(self) -> float:
        return self.t_total_hours + self.p_hard + self.p_sync + self.p_fleet + self.p_direction


def _order_window_iou(order_a: OrderData, order_b: OrderData) -> float:
    a_start = order_a.pickup_ready_at.timestamp()
    a_end = order_a.delivery_deadline_at.timestamp()
    b_start = order_b.pickup_ready_at.timestamp()
    b_end = order_b.delivery_deadline_at.timestamp()

    intersection = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    union = max(a_end, b_end) - min(a_start, b_start)
    if union <= 0:
        return 0.0
    return intersection / union


def _vector_from_warehouse(order: OrderData, warehouse: tuple[float, float]) -> tuple[float, float]:
    wh_lat, wh_lon = warehouse
    return (order.lat - wh_lat, order.lon - wh_lon)


def _cosine_similarity(vector_a: tuple[float, float], vector_b: tuple[float, float]) -> float:
    norm_a = math.hypot(*vector_a)
    norm_b = math.hypot(*vector_b)
    if norm_a == 0 or norm_b == 0:
        return 1.0

    cosine = ((vector_a[0] * vector_b[0]) + (vector_a[1] * vector_b[1])) / (norm_a * norm_b)
    return max(-1.0, min(1.0, cosine))


def _pairwise(values: list[OrderData]) -> Iterable[tuple[OrderData, OrderData]]:
    for index, left in enumerate(values):
        for right in values[index + 1:]:
            yield left, right


def _ordered_trip_orders(trip_orders: list[OrderData], route_ordering: str) -> list[OrderData]:
    if route_ordering == "deadline":
        return sorted(trip_orders, key=lambda order: order.delivery_deadline_at)
    return sorted(trip_orders, key=lambda order: order.order_id)


def evaluate_fitness(
    solution: Solution,
    task_context: TaskContext,
    fitness_config: dict | None = None,
) -> FitnessComponents:
    config = {**DEFAULT_FITNESS_CONFIG, **(fitness_config or {})}
    orders_by_id = {order.order_id: order for order in task_context.orders}

    t_total_hours = 0.0
    p_capacity = 0.0
    p_mass = 0.0
    p_sla = 0.0
    p_sync = 0.0
    p_direction = 0.0
    total_distance_km = 0.0
    late_orders_count = 0
    total_lateness_minutes = 0.0
    max_lateness_minutes = 0.0
    total_orders = 0
    is_valid = True

    active_trips = [trip for trip in solution.trips if trip.order_ids]

    for trip in active_trips:
        trip_orders = [orders_by_id[order_id] for order_id in trip.order_ids]
        total_orders += len(trip_orders)

        p_capacity += config["capacity_penalty_weight"] * max(
            0,
            len(trip_orders) - task_context.constraints.max_order_count,
        )

        total_weight = sum(order.total_mass_kg for order in trip_orders)
        max_allowed_weight = task_context.constraints.max_weight_per_transport[trip.transport_type]
        p_mass += config["mass_penalty_weight"] * max(0.0, total_weight - max_allowed_weight)

        ordered_trip_orders = _ordered_trip_orders(trip_orders, config["route_ordering"])
        current_time = max(order.pickup_ready_at for order in ordered_trip_orders)
        speed_kmh = task_context.constraints.speeds_kmh[trip.transport_type]
        current_lat, current_lon = task_context.warehouses[trip.warehouse_id]

        for order in ordered_trip_orders:
            distance_km = haversine_distance(current_lat, current_lon, order.lat, order.lon)
            travel_time_hours = distance_km / speed_kmh
            current_time += timedelta(hours=travel_time_hours)

            total_distance_km += distance_km
            t_total_hours += travel_time_hours

            lateness_minutes = max(
                0.0,
                (current_time - order.delivery_deadline_at).total_seconds() / 60,
            )
            if lateness_minutes > 0:
                late_orders_count += 1
                total_lateness_minutes += lateness_minutes
                max_lateness_minutes = max(max_lateness_minutes, lateness_minutes)
                p_sla += config["sla_penalty_weight"] * lateness_minutes

            current_lat, current_lon = order.lat, order.lon

        pair_count = 0
        sync_penalty_sum = 0.0
        direction_penalty_sum = 0.0
        warehouse = task_context.warehouses[trip.warehouse_id]

        for left_order, right_order in _pairwise(trip_orders):
            pair_count += 1
            sync_penalty_sum += 1.0 - _order_window_iou(left_order, right_order)

            left_vector = _vector_from_warehouse(left_order, warehouse)
            right_vector = _vector_from_warehouse(right_order, warehouse)
            direction_penalty_sum += 1.0 - _cosine_similarity(left_vector, right_vector)

        if pair_count > 0:
            p_sync += config["sync_weight"] * (sync_penalty_sum / pair_count)
            p_direction += config["direction_weight"] * (direction_penalty_sum / pair_count)

    p_fleet = len(active_trips) * config["fleet_weight"]
    p_hard = p_capacity + p_mass + p_sla
    is_valid = p_hard == 0.0
    avg_orders_per_trip = total_orders / len(active_trips) if active_trips else 0.0

    return FitnessComponents(
        is_valid=is_valid,
        t_total_hours=t_total_hours,
        p_hard=p_hard,
        p_capacity=p_capacity,
        p_mass=p_mass,
        p_sla=p_sla,
        p_sync=p_sync,
        p_fleet=p_fleet,
        p_direction=p_direction,
        total_distance_km=total_distance_km,
        late_orders_count=late_orders_count,
        total_lateness_minutes=total_lateness_minutes,
        max_lateness_minutes=max_lateness_minutes,
        total_orders=total_orders,
        trip_count=len(active_trips),
        avg_orders_per_trip=avg_orders_per_trip,
    )
