import math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from .domain import Individual, Order, Constraint


# --- 1. Standard Distance Metrics ---

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates distance in kilometers between two coordinates."""
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# --- 2. Temporal Intersection Over Union (IUT) Metrics ---

def calculate_temporal_iou(trip_a_start: float, trip_a_end: float,
                           trip_b_start: float, trip_b_end: float) -> float:
    """Calculates the safe 1D Intersection over Union between two time intervals."""
    intersection_start = max(trip_a_start, trip_b_start)
    intersection_end = min(trip_a_end, trip_b_end)
    intersection = max(0.0, intersection_end - intersection_start)

    union_start = min(trip_a_start, trip_b_start)
    union_end = max(trip_a_end, trip_b_end)
    union = max(0.0, union_end - union_start)

    if union <= 0:
        return 0.0
    return intersection / union


def evaluate_clusterization_iut(trip_intervals: List[Tuple[float, float]], iut_weight: float = 50.0) -> float:
    """Evaluates the total Jaccard Distance (1 - IOU) penalty for a set of trips."""
    if len(trip_intervals) < 2:
        return 0.0  # No penalty if there is only 1 or 0 trips

    total_iut_penalty = 0.0
    pairs_compared = 0

    for i in range(len(trip_intervals)):
        for j in range(i + 1, len(trip_intervals)):
            iou = calculate_temporal_iou(
                trip_intervals[i][0], trip_intervals[i][1],
                trip_intervals[j][0], trip_intervals[j][1]
            )
            # Use Jaccard Distance (1 - iou) to penalize lack of overlap
            total_iut_penalty += (1.0 - iou)
            pairs_compared += 1

    average_penalty = total_iut_penalty / pairs_compared
    return average_penalty * iut_weight


# --- 3. Main Fitness Evaluation ---

def evaluate_fitness(individual: Individual, orders: Dict[int, Order], constraints: Constraint,
                     warehouses: Dict[int, Tuple[float, float]]) -> Individual:
    """
    Calculates fitness based on total travel time, standard penalties,
    temporal synchronization (IUT), and fleet size penalty.
    """
    total_time = 0.0
    penalty = 0.0
    is_valid = True

    # Store intervals for IUT and track fleet size
    trip_intervals: List[Tuple[float, float]] = []
    active_fleet_size = 0

    for trip in individual.trips.values():
        if not trip.order_ids:
            continue

        active_fleet_size += 1

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

        # 3. Simulate Route & Time
        trip_orders.sort(key=lambda x: x.delivery_deadline_at)

        # Initialize current_time to the latest pickup_ready_at in the cluster
        current_time = max(o.pickup_ready_at for o in trip_orders)
        trip_start_timestamp = current_time.timestamp()

        speed_kmh = constraints.speeds_kmh[trip.transport_type]
        wh_lat, wh_lon = warehouses[trip.warehouse_id]
        current_lat, current_lon = wh_lat, wh_lon

        # The actual routing loop
        for order in trip_orders:
            dist = haversine_distance(current_lat, current_lon, order.lat, order.lon)
            travel_time_hours = dist / speed_kmh

            current_time += timedelta(hours=travel_time_hours)

            time_diff_seconds = (current_time - order.delivery_deadline_at).total_seconds()
            if time_diff_seconds > 0:
                penalty += 100 * (time_diff_seconds / 60)
                is_valid = False

            current_lat, current_lon = order.lat, order.lon
            total_time += travel_time_hours

        # Record the exact moment the courier finishes the last drop-off
        trip_end_timestamp = current_time.timestamp()
        trip_intervals.append((trip_start_timestamp, trip_end_timestamp))

    # 4. Calculate the temporal overlap penalty (using the intervals captured above)
    sync_penalty = evaluate_clusterization_iut(trip_intervals, iut_weight=10.0)

    # 5. Calculate the Fleet Size Penalty
    fleet_weight = 2.0
    fleet_penalty = active_fleet_size * fleet_weight

    # 6. Final fitness compilation
    individual.fitness_score = total_time + penalty + sync_penalty + fleet_penalty
    individual.is_valid = is_valid

    return individual