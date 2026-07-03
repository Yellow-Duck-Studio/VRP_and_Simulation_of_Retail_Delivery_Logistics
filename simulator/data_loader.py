import json
from datetime import datetime
from typing import Dict, Any

from . import (
    Order, Warehouse, Courier, CourierType, Route, RouteStop, DistanceMatrix, StateManager, Location
)


def parse_datetime(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def load_simulation_data(json_path: str, state_manager: StateManager) -> None:
    """Load data from JSON in StateManager."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data: Dict[str, Any] = json.load(f)

    # Courier types
    for c_type_data in data.get("courier_types", []):
        state_manager.add_courier_type(CourierType(**c_type_data))

    # Warehouses
    for w_data in data.get("warehouses", []):
        state_manager.add_warehouse(Warehouse(**w_data))

    # Orders
    for o_data in data.get("orders", []):
        if isinstance(o_data.get("ready_time"), str):
            o_data["ready_time"] = parse_datetime(o_data["ready_time"])
        if "delivery_time_window" in o_data:
            o_data["delivery_time_window"]["start"] = parse_datetime(o_data["delivery_time_window"]["start"])
            o_data["delivery_time_window"]["end"] = parse_datetime(o_data["delivery_time_window"]["end"])
        state_manager.add_order(Order(**o_data))

    # Couriers
    for c_data in data.get("couriers", []):
        if "last_updated" in c_data and isinstance(c_data["last_updated"], str):
            c_data["last_updated"] = parse_datetime(c_data["last_updated"])
        state_manager.add_courier(Courier(**c_data))

    # Routes
    for r_data in data.get("routes", []):
        if isinstance(r_data.get("start_time"), str):
            r_data["start_time"] = parse_datetime(r_data["start_time"])
        if isinstance(r_data.get("end_time"), str):
            r_data["end_time"] = parse_datetime(r_data["end_time"])
        stops_data = r_data.pop("stops", [])
        route = Route(**r_data)
        for stop_data in stops_data:
            location_data = stop_data.pop("location")
            planned_arrival = stop_data.get("planned_arrival_time")
            if isinstance(planned_arrival, str):
                planned_arrival = parse_datetime(planned_arrival)
            planned_departure = stop_data.get("planned_departure_time")
            if isinstance(planned_departure, str):
                planned_departure = parse_datetime(planned_departure)
            stop = RouteStop(
                order_id=stop_data["order_id"],
                location=Location(**location_data),
                stop_type=stop_data["stop_type"],
                sequence_number=stop_data["sequence_number"],
                service_duration_minutes=stop_data.get("service_duration_minutes", 5),
                planned_arrival_time=planned_arrival,
                planned_departure_time=planned_departure,
            )
            route.stops.append(stop)

        route.stops.sort(key=lambda s: s.sequence_number)
        state_manager.add_route(route)
        for route_id, route in state_manager.routes.items():
            print(f"Route {route_id}: {len(route.stops)} stops")

    # Distance matrices
    raw_matrix = data.get("distance_matrix", [])
    matrix_dict = {}
    for entry in raw_matrix:
        matrix_dict[(entry["from_id"], entry["to_id"])] = float(entry["distance"])
    state_manager.set_distance_matrix(DistanceMatrix.from_dict(matrix_dict))

    # Payment config
    payment_config = data.get("payment_config", {})
    if payment_config:
        state_manager.payment_config = payment_config
    else: # Fallback
        state_manager.payment_config = {
            "rate_per_km": {"car": 50.0, "moped": 40.0, "foot": 25.0},
            "hourly_rate": {"car": 350.0, "moped": 250.0, "foot": 150.0},
            "window_bonus": 100.0,
            "base_fee": 30.0,
            "affiliation_multipliers": {"shift": 1.0, "exchange": 1.2, "3pl": 0.9}
        }