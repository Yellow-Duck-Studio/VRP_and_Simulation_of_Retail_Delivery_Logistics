import json
from datetime import datetime
from typing import Dict, Any

from . import (
    Order, Warehouse, Courier, CourierType, Route, RouteStop, DistanceMatrix, StateManager, Location
)
from .utils.logger import get_logger

logger = get_logger("DataLoader")


def parse_datetime(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def load_simulation_data(json_path: str, state_manager: StateManager) -> None:
    """Load data from JSON in StateManager."""
    logger.info(f"Loading data from {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data: Dict[str, Any] = json.load(f)

    # Courier types
    courier_types_data = data.get("courier_types", [])
    for c_type_data in courier_types_data:
        state_manager.add_courier_type(CourierType(**c_type_data))
    logger.info(f"Loaded {len(courier_types_data)} courier types")

    # Warehouses
    warehouses_data = data.get("warehouses", [])
    for w_data in warehouses_data:
        state_manager.add_warehouse(Warehouse(**w_data))
    logger.info(f"Loaded {len(warehouses_data)} warehouses")

    # Orders
    orders_data = data.get("orders", [])
    for o_data in orders_data:
        if isinstance(o_data.get("ready_time"), str):
            o_data["ready_time"] = parse_datetime(o_data["ready_time"])
        if "delivery_time_window" in o_data:
            o_data["delivery_time_window"]["start"] = parse_datetime(o_data["delivery_time_window"]["start"])
            o_data["delivery_time_window"]["end"] = parse_datetime(o_data["delivery_time_window"]["end"])
        state_manager.add_order(Order(**o_data))
    logger.info(f"Loaded {len(orders_data)} orders")

    # Couriers
    couriers_data = data.get("couriers", [])
    for c_data in couriers_data:
        if "last_updated" in c_data and isinstance(c_data["last_updated"], str):
            c_data["last_updated"] = parse_datetime(c_data["last_updated"])
        state_manager.add_courier(Courier(**c_data))
    logger.info(f"Loaded {len(couriers_data)} couriers")

    # Routes
    routes_data = data.get("routes", [])
    for r_data in routes_data:
        if isinstance(r_data.get("start_time"), str):
            r_data["start_time"] = parse_datetime(r_data["start_time"])
        if isinstance(r_data.get("end_time"), str):
            r_data["end_time"] = parse_datetime(r_data["end_time"])
        stops_data = r_data.pop("stops", [])
        route = Route(**r_data)
        for stop_data in stops_data:
            location_data = stop_data.pop("location")
            stop = RouteStop(
                order_id=stop_data["order_id"],
                location=Location(**location_data),
                stop_type=stop_data["stop_type"],
                sequence_number=stop_data["sequence_number"],
                service_duration_minutes=stop_data.get("service_duration_minutes", 5)
            )
            route.stops.append(stop)
        route.stops.sort(key=lambda s: s.sequence_number)
        state_manager.add_route(route)
        logger.debug(f"Route {route.route_id}: {len(route.stops)} stops")
    logger.info(f"Loaded {len(routes_data)} routes")

    # Distance matrices
    raw_matrix = data.get("distance_matrix", [])
    matrix_dict = {}
    for entry in raw_matrix:
        matrix_dict[(entry["from_id"], entry["to_id"])] = float(entry["distance"])
    state_manager.set_distance_matrix(DistanceMatrix.from_dict(matrix_dict))
    logger.info(f"Loaded {len(raw_matrix)} distance entries")

    # Payment config
    payment_config = data.get("payment_config", {})
    if payment_config:
        state_manager.payment_config = payment_config
        logger.info("Loaded payment config from input")
    else: # Fallback
        state_manager.payment_config = {
            "rate_per_km": {"car": 50.0, "moped": 40.0, "foot": 25.0},
            "hourly_rate": {"car": 350.0, "moped": 250.0, "foot": 150.0},
            "window_bonus": 100.0,
            "base_fee": 30.0,
            "affiliation_multipliers": {"shift": 1.0, "exchange": 1.2, "3pl": 0.9}
        }
        logger.warning("No payment config in input; using fallback defaults")

    logger.info("Data loading complete")