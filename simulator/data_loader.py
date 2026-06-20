import json
from datetime import datetime
from typing import Dict, Any

from . import (
    Order, Warehouse, Courier, CourierType, Route, DistanceMatrix, StateManager
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
        if "time_window" in o_data:
            o_data["time_window"]["start"] = parse_datetime(o_data["time_window"]["start"])
            o_data["time_window"]["end"] = parse_datetime(o_data["time_window"]["end"])
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
        state_manager.add_route(Route(**r_data))

    # Distance matrices
    raw_matrix = data.get("distance_matrix", [])
    matrix_dict = {}
    for entry in raw_matrix:
        matrix_dict[(entry["from_id"], entry["to_id"])] = float(entry["distance"])
    state_manager.set_distance_matrix(DistanceMatrix.from_dict(matrix_dict))