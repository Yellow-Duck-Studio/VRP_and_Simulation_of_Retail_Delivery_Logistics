import pytest
from datetime import datetime, timedelta

@pytest.fixture
def sample_json_data():
    now = datetime.now()
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
                "time_window": {
                    "start": (now - timedelta(minutes=10)).isoformat(),
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
                "affiliation_type": "shift",
                "current_location": {"latitude": 55.7558, "longitude": 37.6173},
                "status": "delivering",
                "current_route_id": "route_1",
                "assigned_order_ids": ["ord_1"]
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
                "end_time": (now + timedelta(minutes=5)).isoformat(),
                "status": "in_progress"
            }
        ],
        "distance_matrix": [
            {"from_id": "wh_1", "to_id": "ord_1", "distance": 2.5}
        ]
    }