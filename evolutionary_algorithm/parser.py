import csv
from datetime import datetime
from typing import List, Dict, Tuple
from evolutionary_algorithm.domain import Order

def load_orders(filepath: str) -> List[Order]:
    orders = []
    with open(filepath, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # We filter by task_id = 1 for a single run, or process all
            if row['task_id'] == '1':
                orders.append(Order(
                    order_id=int(row['order_id']),
                    warehouse_id=int(row['warehouse_id']),
                    lat=float(row['order_lat']),
                    lon=float(row['order_lon']),
                    pickup_ready_at=datetime.fromisoformat(row['pickup_ready_at']),
                    delivery_deadline_at=datetime.fromisoformat(row['delivery_deadline_at']),
                    total_mass_kg=float(row['total_mass_kg'])
                ))
    return orders

def load_warehouses(filepath: str) -> Dict[int, Tuple[float, float]]:
    warehouses = {}
    with open(filepath, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
             if row['task_id'] == '1':
                warehouses[int(row['warehouse_id'])] = (float(row['lat']), float(row['lon']))
    return warehouses

def load_transport_constraints(filepath: str) -> Tuple[Dict[str, float], Dict[str, float]]:
    speeds = {}
    payloads = {}
    with open(filepath, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row['code']
            speeds[code] = float(row['approx_speed_kmh'])
            payloads[code] = float(row['max_payload_kg'])
    return speeds, payloads