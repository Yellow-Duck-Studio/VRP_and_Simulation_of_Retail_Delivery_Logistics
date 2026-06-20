from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from evolutionary_algorithm.domain import Constraint, Individual, Order, Trip
from heuristics.core_utils import haversine_distance, select_transport_type
from heuristics.evaluation import evaluate_individual


@dataclass
class SavingsRoute:
    warehouse_id: int
    order_ids: List[int]


def _can_merge_routes(
    left_route: SavingsRoute,
    right_route: SavingsRoute,
    orders: Dict[int, Order],
    constraints: Constraint,
) -> bool:
    if left_route.warehouse_id != right_route.warehouse_id:
        return False

    merged_order_ids = left_route.order_ids + right_route.order_ids
    if len(merged_order_ids) > constraints.max_order_count:
        return False

    transport_type = select_transport_type(merged_order_ids, orders, constraints)
    total_weight = sum(orders[order_id].total_mass_kg for order_id in merged_order_ids)
    return total_weight <= constraints.max_weight_per_transport[transport_type]


def build_clarke_wright_solution(
    orders: List[Order],
    warehouses_dict: Dict[int, Tuple[float, float]],
    constraints: Constraint,
) -> Individual:
    orders_dict = {order.order_id: order for order in orders}
    routes_by_order: Dict[int, SavingsRoute] = {
        order.order_id: SavingsRoute(
            warehouse_id=order.warehouse_id,
            order_ids=[order.order_id],
        )
        for order in orders
    }

    orders_by_warehouse: Dict[int, List[Order]] = {}
    for order in orders:
        orders_by_warehouse.setdefault(order.warehouse_id, []).append(order)

    for warehouse_id, warehouse_orders in orders_by_warehouse.items():
        depot_lat, depot_lon = warehouses_dict[warehouse_id]
        savings_candidates = []

        for index, left_order in enumerate(warehouse_orders):
            for right_order in warehouse_orders[index + 1:]:
                savings = (
                    haversine_distance(depot_lat, depot_lon, left_order.lat, left_order.lon)
                    + haversine_distance(depot_lat, depot_lon, right_order.lat, right_order.lon)
                    - haversine_distance(left_order.lat, left_order.lon, right_order.lat, right_order.lon)
                )
                savings_candidates.append((savings, left_order.order_id, right_order.order_id))

        savings_candidates.sort(reverse=True)

        for _, left_order_id, right_order_id in savings_candidates:
            left_route = routes_by_order[left_order_id]
            right_route = routes_by_order[right_order_id]
            if left_route is right_route:
                continue

            merged_route = None
            orientations = (
                (left_route.order_ids, right_route.order_ids),
                (list(reversed(left_route.order_ids)), right_route.order_ids),
                (left_route.order_ids, list(reversed(right_route.order_ids))),
                (list(reversed(left_route.order_ids)), list(reversed(right_route.order_ids))),
            )

            for left_ids, right_ids in orientations:
                candidate_left = SavingsRoute(warehouse_id=warehouse_id, order_ids=list(left_ids))
                candidate_right = SavingsRoute(warehouse_id=warehouse_id, order_ids=list(right_ids))
                if _can_merge_routes(candidate_left, candidate_right, orders_dict, constraints):
                    merged_route = SavingsRoute(
                        warehouse_id=warehouse_id,
                        order_ids=candidate_left.order_ids + candidate_right.order_ids,
                    )
                    break

            if merged_route is None:
                continue

            for order_id in merged_route.order_ids:
                routes_by_order[order_id] = merged_route

    unique_routes = []
    seen_routes = set()
    for route in routes_by_order.values():
        route_key = tuple(route.order_ids)
        if route_key in seen_routes:
            continue
        seen_routes.add(route_key)
        unique_routes.append(route)

    individual = Individual()
    for trip_id, route in enumerate(unique_routes, start=1):
        transport_type = select_transport_type(route.order_ids, orders_dict, constraints)
        individual.trips[trip_id] = Trip(
            trip_id=trip_id,
            warehouse_id=route.warehouse_id,
            transport_type=transport_type,
            order_ids=list(route.order_ids),
        )

    return evaluate_individual(individual, orders_dict, constraints, warehouses_dict)
