import pytest
import json
import tempfile
from datetime import datetime, timedelta

from simulator import (
    SimulationController, load_simulation_data
)
from simulator.core import EventType

def test_full_simulation_delivery(temp_json_file):
    start_time = datetime.now() + timedelta(minutes=5)
    controller = SimulationController(start_time=start_time, time_step_minutes=1)
    load_simulation_data(temp_json_file, controller.state_manager)

    controller.run(max_steps=30)

    results = controller.get_results()
    delivery_time_str = results["order_delivery_times"]["ord_1"]
    assert delivery_time_str is not None
    delivery_dt = datetime.fromisoformat(delivery_time_str)
    assert delivery_dt >= start_time

    assert results["order_delivered_in_window"]["ord_1"] is True

    payment_events = controller.event_manager.get_events(EventType.PAYMENT_SENT)
    assert len(payment_events) == 1

    order = controller.state_manager.get_order("ord_1")
    assert order.status == "delivered"

    courier = controller.state_manager.couriers["cour_1"]
    assert courier.status == "idle"

def test_order_not_ready():
    """Order is not ready before start"""
    # for future
    pass