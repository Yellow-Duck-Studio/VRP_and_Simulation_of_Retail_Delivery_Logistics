import csv
from datetime import datetime
from typing import List, Dict, Tuple
from evolutionary_algorithm.domain import Order


def load_all_orders(filepath: str) -> Dict[str, List[Order]]:
    """Reads the CSV and groups all orders by their task_id."""
    tasks_orders = {}
    with open(filepath, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            task_id = row['task_id']
            if task_id not in tasks_orders:
                tasks_orders[task_id] = []

            tasks_orders[task_id].append(Order(
                order_id=int(row['order_id']),
                warehouse_id=int(row['warehouse_id']),
                lat=float(row['order_lat']),
                lon=float(row['order_lon']),
                pickup_ready_at=datetime.fromisoformat(row['pickup_ready_at']),
                delivery_deadline_at=datetime.fromisoformat(row['delivery_deadline_at']),
                total_mass_kg=float(row['total_mass_kg'])
            ))
    return tasks_orders


def load_all_warehouses(filepath: str) -> Dict[str, Dict[int, Tuple[float, float]]]:
    """Reads the CSV and groups warehouses by task_id."""
    tasks_warehouses = {}
    with open(filepath, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            task_id = row['task_id']
            if task_id not in tasks_warehouses:
                tasks_warehouses[task_id] = {}

            tasks_warehouses[task_id][int(row['warehouse_id'])] = (float(row['lat']), float(row['lon']))
    return tasks_warehouses


def load_transport_constraints(filepath: str) -> Tuple[
    Dict[str, float],
    Dict[str, float],
    Dict[str, float],
    Dict[str, float],
    Dict[str, float],
    Dict[str, float]
]:
    """Loads speed and payload constraints. (These are universal, not task-specific)"""
    speeds = {}
    payloads = {}
    fixed_fee = {}
    per_km_fee = {}
    per_order_fee = {}
    per_kg_min_fee = {}
    with open(filepath, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row['code']
            speeds[code] = float(row['approx_speed_kmh'])
            payloads[code] = float(row['max_payload_kg'])
            fixed_fee[code] = float(row['fixed_fee'])
            per_km_fee[code] = float(row['per_km_fee'])
            per_order_fee[code] = float(row['per_order_fee'])
            per_kg_min_fee[code] = float(row['per_kg_min_fee'])
    return speeds, payloads, fixed_fee, per_km_fee, per_order_fee, per_kg_min_fee
