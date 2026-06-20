from __future__ import annotations

from datetime import timedelta
from typing import Dict, Tuple

from evolutionary_algorithm.domain import Constraint, Individual, Order
from heuristics.core_utils import haversine_distance


def evaluate_individual(
    individual: Individual,
    orders: Dict[int, Order],
    constraints: Constraint,
    warehouses: Dict[int, Tuple[float, float]],
) -> Individual:
    total_time = 0.0
    penalty = 0.0
    is_valid = True

    for trip in individual.trips.values():
        if not trip.order_ids:
            continue

        trip_orders = [orders[order_id] for order_id in trip.order_ids]

        if len(trip_orders) > constraints.max_order_count:
            penalty += 1000 * (len(trip_orders) - constraints.max_order_count)
            is_valid = False

        total_weight = sum(order.total_mass_kg for order in trip_orders)
        max_allowed_weight = constraints.max_weight_per_transport[trip.transport_type]
        if total_weight > max_allowed_weight:
            penalty += 500 * (total_weight - max_allowed_weight)
            is_valid = False

        trip_orders.sort(key=lambda order: order.delivery_deadline_at)
        current_time = max(order.pickup_ready_at for order in trip_orders)
        speed_kmh = constraints.speeds_kmh[trip.transport_type]

        current_lat, current_lon = warehouses[trip.warehouse_id]
        for order in trip_orders:
            distance_km = haversine_distance(current_lat, current_lon, order.lat, order.lon)
            travel_time_hours = distance_km / speed_kmh
            current_time += timedelta(hours=travel_time_hours)

            lateness_seconds = (current_time - order.delivery_deadline_at).total_seconds()
            if lateness_seconds > 0:
                penalty += 100 * (lateness_seconds / 60)
                is_valid = False

            current_lat, current_lon = order.lat, order.lon
            total_time += travel_time_hours

    individual.fitness_score = total_time + penalty
    individual.is_valid = is_valid
    return individual
