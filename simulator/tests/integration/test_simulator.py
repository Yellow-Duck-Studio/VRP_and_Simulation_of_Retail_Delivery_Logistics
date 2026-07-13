import pytest
import json
import tempfile
from datetime import datetime, timedelta

from simulator import (
    SimulationController, load_simulation_data
)

@pytest.fixture
def temp_json_file(sample_json_data):
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        json.dump(sample_json_data, f)
        temp_path = f.name
    yield temp_path
    import os
    os.unlink(temp_path)


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
