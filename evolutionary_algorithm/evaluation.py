import math
from datetime import datetime
from typing import Dict, Tuple

from evolutionary_algorithm.domain import Individual, Constraint, Order


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates distance in kilometers between two coordinates."""
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


from datetime import datetime, timedelta
from typing import Dict, List, Tuple


def evaluate_fitness(individual: Individual, orders: Dict[int, Order], constraints: Constraint,
                     warehouses: Dict[int, Tuple[float, float]]) -> Individual:
    """
    Calculates fitness based on total travel time, penalized by constraint violations.
    Lower score is better.
    """
    total_time = 0.0
    penalty = 0.0
    is_valid = True

    for trip in individual.trips.values():
        if not trip.order_ids:
            continue

        trip_orders = [orders[oid] for oid in trip.order_ids]

        # 1. Constraint: Max Orders
        if len(trip_orders) > constraints.max_order_count:
            penalty += 1000 * (len(trip_orders) - constraints.max_order_count)
            is_valid = False

        # 2. Constraint: Max Weight
        total_weight = sum(o.total_mass_kg for o in trip_orders)
        max_allowed_weight = constraints.max_weight_per_transport[trip.transport_type]
        if total_weight > max_allowed_weight:
            penalty += 500 * (total_weight - max_allowed_weight)
            is_valid = False

        # 3. Simulate Route & Time (Greedy / Sorted by deadline)
        trip_orders.sort(key=lambda x: x.delivery_deadline_at)
        current_time = max(o.pickup_ready_at for o in trip_orders)  # Wait for all orders to be ready
        speed_kmh = constraints.speeds_kmh[trip.transport_type]

        wh_lat, wh_lon = warehouses[trip.warehouse_id]
        current_lat, current_lon = wh_lat, wh_lon

        for order in trip_orders:
            dist = haversine_distance(current_lat, current_lon, order.lat, order.lon)
            travel_time_hours = dist / speed_kmh

            # Fix: Advance the datetime object using timedelta
            current_time += timedelta(hours=travel_time_hours)

            # Simulated time vs Deadline using proper datetime comparison
            # Subtracting two datetimes yields a timedelta object
            time_diff_seconds = (current_time - order.delivery_deadline_at).total_seconds()

            if time_diff_seconds > 0:
                penalty += 100 * (time_diff_seconds / 60)  # Penalty per minute late
                is_valid = False

            current_lat, current_lon = order.lat, order.lon
            total_time += travel_time_hours

    individual.fitness_score = total_time + penalty
    individual.is_valid = is_valid
    return individual