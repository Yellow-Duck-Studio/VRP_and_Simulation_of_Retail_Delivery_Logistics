import pytest
import json
import tempfile
from datetime import datetime, timedelta

@pytest.fixture
def sample_json_data():
    now = datetime.now()
    start = now + timedelta(minutes=5)
    return {
        "courier_types": [
            {"type_id": "car_1", "name": "Car", "capacity_kg": 100.0, "speed_kmh": 60.0}
        ],
        "warehouses": [
            {
                "warehouse_id": "wh_1",
                "location": {"latitude": 55.7558, "longitude": 37.6173, "address": "Center"}
            }
        ],
        "orders": [
            {
                "order_id": "ord_1",
                "warehouse_id": "wh_1",
                "delivery_location": {"latitude": 55.75, "longitude": 37.61},
                "delivery_time_window": {
                    "start": now.isoformat(),
                    "end": (now + timedelta(minutes=60)).isoformat()
                },
                "mass_kg": 5.0,
                "ready_time": now.isoformat(),
                "status": "pending"
            }
        ],
        "couriers": [
            {
                "courier_id": "cour_1",
                "courier_type_id": "car_1",
                "affiliation_type": "exchange",
                "current_location": {"latitude": 55.7558, "longitude": 37.6173},
                "status": "idle",
                "current_route_id": None,
                "assigned_order_ids": [],
                "planned_route_ids": ["route_1"]
            }
        ],
        "routes": [
            {
                "route_id": "route_1",
                "courier_id": "cour_1",
                "warehouse_id": "wh_1",
                "start_location": {"latitude": 55.7558, "longitude": 37.6173},
                "end_location": {"latitude": 55.75, "longitude": 37.61},
                "start_time": now.isoformat(),
                "end_time": (now + timedelta(minutes=30)).isoformat(),
                "total_distance_km": 5.0,
                "total_duration_minutes": 30,
                "stops": [
                    {
                        "order_id": "ord_1",
                        "location": {"latitude": 55.7558, "longitude": 37.6173},
                        "stop_type": "pickup",
                        "sequence_number": 1,
                        "service_duration_minutes": 5
                    },
                    {
                        "order_id": "ord_1",
                        "location": {"latitude": 55.75, "longitude": 37.61},
                        "stop_type": "delivery",
                        "sequence_number": 2,
                        "service_duration_minutes": 3
                    }
                ]
            }
        ],
        "distance_matrix": [
            {"from_id": "wh_1", "to_id": "ord_1", "distance": 2.5}
        ],
        "payment_config": {
            "rate_per_km": {"car_1": 60.0, "car": 60.0, "moped": 45.0, "foot": 25.0},
            "hourly_rate": {"car_1": 400.0, "car": 400.0, "moped": 300.0, "foot": 200.0},
            "window_bonus": 150.0,
            "base_fee": 50.0,
            "affiliation_multipliers": {"shift": 1.0, "exchange": 1.2, "3pl": 0.9}
        }
    }

@pytest.fixture
def temp_json_file(sample_json_data):
    """Creates temporary JSON-file with test data"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        json.dump(sample_json_data, f)
        temp_path = f.name
    return temp_path