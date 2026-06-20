from __future__ import annotations

import math
from typing import Dict, Iterable, List, Tuple

from evolutionary_algorithm.domain import Constraint, Individual, Order, Trip


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r_km * c


def clone_trip(trip: Trip) -> Trip:
    return Trip(
        trip_id=trip.trip_id,
        warehouse_id=trip.warehouse_id,
        transport_type=trip.transport_type,
        order_ids=list(trip.order_ids),
    )


def clone_individual(individual: Individual) -> Individual:
    return Individual(
        trips={trip_id: clone_trip(trip) for trip_id, trip in individual.trips.items()},
        fitness_score=individual.fitness_score,
        is_valid=individual.is_valid,
    )


def feasible_transport_types(
    order_ids: Iterable[int],
    orders: Dict[int, Order],
    constraints: Constraint,
) -> List[str]:
    total_weight = sum(orders[order_id].total_mass_kg for order_id in order_ids)
    return [
        transport_type
        for transport_type, max_weight in constraints.max_weight_per_transport.items()
        if total_weight <= max_weight
    ]


def select_transport_type(
    order_ids: Iterable[int],
    orders: Dict[int, Order],
    constraints: Constraint,
) -> str:
    feasible = feasible_transport_types(order_ids, orders, constraints)
    if not feasible:
        return max(
            constraints.max_weight_per_transport,
            key=constraints.max_weight_per_transport.get,
        )
    return max(feasible, key=lambda name: constraints.speeds_kmh[name])


def next_trip_id(individual: Individual) -> int:
    return max(individual.trips.keys(), default=0) + 1


def canonical_signature(individual: Individual) -> Tuple[Tuple[int, str, Tuple[int, ...]], ...]:
    signature = []
    for trip in individual.trips.values():
        if not trip.order_ids:
            continue
        signature.append(
            (
                trip.warehouse_id,
                trip.transport_type,
                tuple(sorted(trip.order_ids)),
            )
        )
    return tuple(sorted(signature))
