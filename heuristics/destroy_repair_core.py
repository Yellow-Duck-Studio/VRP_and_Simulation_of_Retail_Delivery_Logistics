from __future__ import annotations

import random
from typing import Dict, List, Tuple

from evolutionary_algorithm.domain import Constraint, Individual, Order, Trip
from heuristics.core_utils import canonical_signature, clone_individual, next_trip_id, select_transport_type
from heuristics.evaluation import evaluate_individual


def _ordered_active_trip_ids(individual: Individual) -> List[int]:
    return [
        trip.trip_id
        for trip in sorted(individual.trips.values(), key=lambda trip: len(trip.order_ids), reverse=True)
        if trip.order_ids
    ]


def _destroy(
    individual: Individual,
    orders: Dict[int, Order],
    constraints: Constraint,
    rng: random.Random,
    destroy_fraction: float,
) -> List[int]:
    removed_order_ids: List[int] = []
    active_trip_ids = _ordered_active_trip_ids(individual)
    if not active_trip_ids:
        return removed_order_ids

    total_orders = sum(len(trip.order_ids) for trip in individual.trips.values())
    target_removed = max(1, int(total_orders * destroy_fraction))

    for trip_id in active_trip_ids:
        trip = individual.trips[trip_id]
        trip_orders = [orders[order_id] for order_id in trip.order_ids]
        trip_orders.sort(key=lambda order: order.delivery_deadline_at)

        late_pressure = max(1, len(trip_orders) // 2)
        for order in trip_orders[-late_pressure:]:
            if len(removed_order_ids) >= target_removed:
                break
            if order.order_id in trip.order_ids:
                trip.order_ids.remove(order.order_id)
                removed_order_ids.append(order.order_id)
        if len(removed_order_ids) >= target_removed:
            break

    if len(removed_order_ids) < target_removed:
        remaining_order_ids = [
            order_id
            for trip in individual.trips.values()
            for order_id in trip.order_ids
        ]
        rng.shuffle(remaining_order_ids)
        for order_id in remaining_order_ids:
            if len(removed_order_ids) >= target_removed:
                break
            for trip in individual.trips.values():
                if order_id in trip.order_ids:
                    trip.order_ids.remove(order_id)
                    removed_order_ids.append(order_id)
                    break

    for trip in individual.trips.values():
        if trip.order_ids:
            trip.transport_type = select_transport_type(trip.order_ids, orders, constraints)

    return removed_order_ids


def _can_insert(
    trip: Trip,
    order_id: int,
    orders: Dict[int, Order],
    constraints: Constraint,
) -> bool:
    new_order_ids = trip.order_ids + [order_id]
    if len(new_order_ids) > constraints.max_order_count:
        return False

    transport_type = select_transport_type(new_order_ids, orders, constraints)
    total_weight = sum(orders[current_order_id].total_mass_kg for current_order_id in new_order_ids)
    return total_weight <= constraints.max_weight_per_transport[transport_type]


def _repair(
    individual: Individual,
    removed_order_ids: List[int],
    orders: Dict[int, Order],
    warehouses_dict: Dict[int, Tuple[float, float]],
    constraints: Constraint,
) -> Individual:
    for order_id in removed_order_ids:
        order = orders[order_id]
        best_candidate = None
        best_score = float("inf")

        for trip in individual.trips.values():
            if not trip.order_ids or trip.warehouse_id != order.warehouse_id:
                continue
            if not _can_insert(trip, order_id, orders, constraints):
                continue

            candidate = clone_individual(individual)
            candidate.trips[trip.trip_id].order_ids.append(order_id)
            candidate.trips[trip.trip_id].transport_type = select_transport_type(
                candidate.trips[trip.trip_id].order_ids,
                orders,
                constraints,
            )
            evaluate_individual(candidate, orders, constraints, warehouses_dict)

            if candidate.fitness_score < best_score:
                best_candidate = candidate
                best_score = candidate.fitness_score

        if best_candidate is None:
            candidate = clone_individual(individual)
            trip_id = next_trip_id(candidate)
            candidate.trips[trip_id] = Trip(
                trip_id=trip_id,
                warehouse_id=order.warehouse_id,
                transport_type=select_transport_type([order_id], orders, constraints),
                order_ids=[order_id],
            )
            evaluate_individual(candidate, orders, constraints, warehouses_dict)
            individual = candidate
        else:
            individual = best_candidate

    return individual


def run_destroy_repair(
    seed_individual: Individual,
    orders: List[Order],
    warehouses_dict: Dict[int, Tuple[float, float]],
    constraints: Constraint,
    iterations: int = 200,
    destroy_fraction: float = 0.2,
    max_solutions: int = 100,
    rng_seed: int = 42,
) -> List[Individual]:
    rng = random.Random(rng_seed)
    orders_dict = {order.order_id: order for order in orders}

    current = clone_individual(seed_individual)
    evaluate_individual(current, orders_dict, constraints, warehouses_dict)

    best = clone_individual(current)
    solutions = []
    seen_signatures = set()

    if best.is_valid:
        seen_signatures.add(canonical_signature(best))
        solutions.append(clone_individual(best))

    for _ in range(iterations):
        candidate = clone_individual(best)
        removed_order_ids = _destroy(candidate, orders_dict, constraints, rng, destroy_fraction)
        candidate = _repair(candidate, removed_order_ids, orders_dict, warehouses_dict, constraints)
        evaluate_individual(candidate, orders_dict, constraints, warehouses_dict)

        if candidate.fitness_score <= best.fitness_score:
            best = clone_individual(candidate)

        if candidate.is_valid:
            signature = canonical_signature(candidate)
            if signature not in seen_signatures:
                seen_signatures.add(signature)
                solutions.append(clone_individual(candidate))
                if len(solutions) >= max_solutions:
                    break

    return sorted(solutions, key=lambda item: item.fitness_score)
