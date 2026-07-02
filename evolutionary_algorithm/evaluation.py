import math
from datetime import timedelta
from typing import Dict, List, Tuple
from evolutionary_algorithm.domain import Individual, Order, Constraint, Economics



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

# --- 3. Cosine Similarity ---

def calculate_directional_penalty(wh_lat: float, wh_lon: float,
                                  lat1: float, lon1: float,
                                  lat2: float, lon2: float) -> float:
    """Calculates the angular penalty (1 - Cosine Similarity) between two orders relative to the warehouse."""

    # Correct for Earth's curvature at this specific latitude so our "pizza slices" are accurate
    lat_rad = math.radians(wh_lat)

    # Vector A (Warehouse -> Order 1)
    dy1 = lat1 - wh_lat
    dx1 = (lon1 - wh_lon) * math.cos(lat_rad)

    # Vector B (Warehouse -> Order 2)
    dy2 = lat2 - wh_lat
    dx2 = (lon2 - wh_lon) * math.cos(lat_rad)

    # Calculate magnitudes (radii)
    mag1 = math.sqrt(dx1 ** 2 + dy1 ** 2)
    mag2 = math.sqrt(dx2 ** 2 + dy2 ** 2)

    # If an order is physically AT the warehouse, it has no angle. Return 0 penalty.
    if mag1 == 0 or mag2 == 0:
        return 0.0

        # Dot product
    dot_product = (dx1 * dx2) + (dy1 * dy2)

    # Cosine similarity (clamped between -1 and 1 to prevent float rounding crashes)
    cos_theta = max(-1.0, min(1.0, dot_product / (mag1 * mag2)))

    # Convert to penalty: 0.0 (same direction) to 2.0 (opposite directions)
    return 1.0 - cos_theta


def evaluate_cluster_direction(wh_lat: float, wh_lon: float, trip_orders: List[Order]) -> float:
    """Averages the directional penalty for all pairs of orders in a single courier's trip."""
    if len(trip_orders) < 2:
        return 0.0  # No penalty for a 1-order trip

    total_penalty = 0.0
    pairs_compared = 0

    for i in range(len(trip_orders)):
        for j in range(i + 1, len(trip_orders)):
            penalty = calculate_directional_penalty(
                wh_lat, wh_lon,
                trip_orders[i].lat, trip_orders[i].lon,
                trip_orders[j].lat, trip_orders[j].lon
            )
            total_penalty += penalty
            pairs_compared += 1

    return total_penalty / pairs_compared


# --- 4. Main Fitness Evaluation ---

def evaluate_fitness(individual: Individual, orders: Dict[int, Order],
                     constraints: Constraint, warehouses: Dict[int, Tuple[float, float]],
                     econ: Economics) -> Individual:
    """
    Calculates individual fitness score expressed in real money (currency units).
    Combines direct logistics costs with financial risks of SLA violations.
    """
    total_cost_rub = 0.0
    is_valid = True
    warehouse_trip_intervals: Dict[int, List[Tuple[float, float]]] = {}

    for trip in individual.trips.values():
        if not trip.order_ids:
            continue

        trip_orders = [orders[oid] for oid in trip.order_ids]

        # 1. Base courier fees
        trip_cost = econ.fixed_fee + (len(trip_orders) * econ.per_order_fee)

        # 2. Hard constraints check (Order count & Weight capacity)
        if len(trip_orders) > constraints.max_order_count:
            trip_cost += econ.invalid_route_penalty
            is_valid = False

        total_weight = sum(o.total_mass_kg for o in trip_orders)
        max_allowed_weight = constraints.max_weight_per_transport[trip.transport_type]
        if total_weight > max_allowed_weight:
            trip_cost += econ.invalid_route_penalty
            is_valid = False

        # 3. Route & Time simulation setup
        trip_orders.sort(key=lambda x: x.delivery_deadline_at)
        current_time = max(o.pickup_ready_at for o in trip_orders)
        trip_start_timestamp = current_time.timestamp()

        speed_kmh = constraints.speeds_kmh[trip.transport_type]
        wh_lat, wh_lon = warehouses[trip.warehouse_id]
        current_lat, current_lon = wh_lat, wh_lon

        current_load_kg = total_weight
        trip_kg_min = 0.0
        trip_distance_km = 0.0

        # 4. Shape penalty (Adds up to 20% to distance cost for bad routing geometry)
        cluster_spread = evaluate_cluster_direction(wh_lat, wh_lon, trip_orders)
        direction_multiplier = 1.0 + (cluster_spread * 0.2)

        # 5. Core trip simulation loop
        for order in trip_orders:
            dist_km = haversine_distance(current_lat, current_lon, order.lat, order.lon)
            trip_distance_km += dist_km

            travel_time_hours = dist_km / speed_kmh
            travel_time_mins = travel_time_hours * 60.0

            # Laboratory metrics (mass-time accumulation)
            trip_kg_min += current_load_kg * travel_time_mins
            current_time += timedelta(hours=travel_time_hours)

            # SLA Deadline verification
            time_diff_seconds = (current_time - order.delivery_deadline_at).total_seconds()
            if time_diff_seconds > 0:
                late_mins = time_diff_seconds / 60.0
                trip_cost += late_mins * econ.sla_penalty_per_min
                is_valid = False

                # Offload current order weight
            current_load_kg -= order.total_mass_kg
            current_lat, current_lon = order.lat, order.lon

        trip_end_timestamp = current_time.timestamp()
        warehouse_trip_intervals.setdefault(trip.warehouse_id, []).append((trip_start_timestamp, trip_end_timestamp))

        # 6. Aggregate trip costs
        trip_cost += (trip_distance_km * econ.per_km_fee * direction_multiplier)
        trip_cost += (trip_kg_min * econ.per_kg_min_fee)
        total_cost_rub += trip_cost

    # 7. Global warehouse synchronization penalty
    total_sync_penalty_ratio = 0.0
    for wh_id, intervals in warehouse_trip_intervals.items():
        total_sync_penalty_ratio += evaluate_clusterization_iut(intervals, iut_weight=1.0)
    total_cost_rub += total_sync_penalty_ratio * econ.warehouse_sync_cost

    individual.fitness_score = total_cost_rub
    individual.is_valid = is_valid
    return individual

def evaluate_fitness_outdated(individual: Individual, orders: Dict[int, Order], constraints: Constraint,
                     warehouses: Dict[int, Tuple[float, float]]) -> Individual:
    """
    Calculates fitness based on time, penalties, IUT, fleet size, AND directional cohesion.
    """
    total_time = 0.0
    penalty = 0.0
    is_valid = True

    trip_intervals: List[Tuple[float, float]] = []
    active_fleet_size = 0

    # Keep a running total of how "spread out" the clusters are
    total_direction_penalty = 0.0

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

        current_time = max(o.pickup_ready_at for o in trip_orders)
        trip_start_timestamp = current_time.timestamp()

        speed_kmh = constraints.speeds_kmh[trip.transport_type]
        wh_lat, wh_lon = warehouses[trip.warehouse_id]

        # 4. Evaluate Directional Cohesion (The new "Sweep" metric)
        # We calculate this once per trip before they start driving
        cluster_spread = evaluate_cluster_direction(wh_lat, wh_lon, trip_orders)
        total_direction_penalty += cluster_spread

        current_lat, current_lon = wh_lat, wh_lon

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

        trip_end_timestamp = current_time.timestamp()
        trip_intervals.append((trip_start_timestamp, trip_end_timestamp))

    # 5. Temporal overlap penalty
    sync_penalty = evaluate_clusterization_iut(trip_intervals, iut_weight=50.0)

    # 6. Fleet Size Penalty
    fleet_penalty = active_fleet_size * 2.0

    # 7. Directional Penalty Weight
    # (e.g., 5.0 hours of equivalent penalty for a terrible North/South route)
    direction_weight = 5.0
    weighted_direction_penalty = total_direction_penalty * direction_weight

    # Final fitness compilation
    individual.fitness_score = total_time + penalty + sync_penalty + fleet_penalty + weighted_direction_penalty
    individual.is_valid = is_valid

    return individual