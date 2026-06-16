import pytest
import json
import tempfile
from datetime import datetime, timedelta

from simulator import (
    SimulationController, load_simulation_data
)


@pytest.fixture
def sample_json_data():
    now = datetime.now()
    return {
        "courier_types": [
            {"type_id": "auto_1", "name": "Auto", "capacity_kg": 100.0, "speed_kmh": 60.0}
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
                "customer_id": "cust_1",
                "warehouse_id": "wh_1",
                "location": {"latitude": 55.75, "longitude": 37.61},
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
                "courier_type_id": "auto_1",
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
                "transport_id": "cour_1",
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


@pytest.fixture
def temp_json_file(sample_json_data):
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        json.dump(sample_json_data, f)
        temp_path = f.name
    return temp_path


def test_reader_loads_data(temp_json_file):
    controller = SimulationController(start_time=datetime.now())
    load_simulation_data(temp_json_file, controller.state_manager)

    assert len(controller.state_manager.courier_types) == 1
    assert len(controller.state_manager.warehouses) == 1
    assert len(controller.state_manager.orders) == 1
    assert len(controller.state_manager.couriers) == 1
    assert len(controller.state_manager.routes) == 1

    matrix = controller.state_manager.distance_matrix
    assert matrix is not None
    assert matrix.get_distance("wh_1", "ord_1") == 2.5


def test_simulation_step_advances_time(temp_json_file):
    start_time = datetime.now()
    time_step = 10
    controller = SimulationController(start_time=start_time, time_step_minutes=time_step)
    load_simulation_data(temp_json_file, controller.state_manager)

    assert controller.time_manager.current_time == start_time
    assert len(controller.state_manager.history) == 0

    controller.step()

    expected_time = start_time + timedelta(minutes=time_step)
    assert controller.time_manager.current_time == expected_time
    assert len(controller.state_manager.history) == 1
