import pytest
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from simulator import (
    SimulationController, load_simulation_data
)
from simulator.engine import EventType
from simulator.schemas import OrderStatus

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

def test_capacity_exceeded():
    """
    Test that when an order exceeds courier capacity, it is skipped and not delivered.
    """
    now = datetime.now()
    start_time = now + timedelta(minutes=5)
    data = {
        "payment_config": {
            "rate_per_km": {"car": 50.0},
            "window_bonus": 100.0,
            "base_fee": 0.0,
            "affiliation_multipliers": {"shift": 1.0}
        },
        "courier_types": [
            {"type_id": "car", "name": "Car", "capacity_kg": 10.0, "speed_kmh": 60.0}
        ],
        "warehouses": [
            {
                "warehouse_id": "wh_1",
                "location": {"latitude": 55.7558, "longitude": 37.6173}
            }
        ],
        "orders": [
            {
                "order_id": "heavy_order",
                "warehouse_id": "wh_1",
                "delivery_location": {"latitude": 55.75, "longitude": 37.61},
                "delivery_time_window": {
                    "start": (start_time + timedelta(minutes=10)).isoformat(),
                    "end": (start_time + timedelta(minutes=60)).isoformat()
                },
                "mass_kg": 15.0,  # Exceeds courier capacity (10 kg)
                "ready_time": (start_time + timedelta(minutes=5)).isoformat()
            }
        ],
        "couriers": [
            {
                "courier_id": "cour_1",
                "courier_type_id": "car",
                "affiliation_type": "shift",
                "current_location": {"latitude": 55.7558, "longitude": 37.6173},
                "status": "idle",
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
                "start_time": (start_time + timedelta(minutes=5)).isoformat(),
                "end_time": (start_time + timedelta(minutes=30)).isoformat(),
                "total_distance_km": 2.5,
                "total_duration_minutes": 25,
                "stops": [
                    {
                        "order_id": "heavy_order",
                        "location": {"latitude": 55.7558, "longitude": 37.6173},
                        "stop_type": "pickup",
                        "sequence_number": 1,
                        "service_duration_minutes": 5
                    },
                    {
                        "order_id": "heavy_order",
                        "location": {"latitude": 55.75, "longitude": 37.61},
                        "stop_type": "delivery",
                        "sequence_number": 2,
                        "service_duration_minutes": 3
                    }
                ]
            }
        ],
        "distance_matrix": [
            {"from_id": "wh_1", "to_id": "heavy_order", "distance": 2.5},
            {"from_id": "heavy_order", "to_id": "heavy_order", "distance": 0.0}
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(data, f)
        temp_path = f.name

    try:
        controller = SimulationController(
            start_time=start_time,
            time_step_minutes=1,
            strict_validation=False
        )
        load_simulation_data(temp_path, controller.state_manager)

        controller.run(max_steps=50)

        results = controller.get_results()
        order_delivery_time = results["order_delivery_times"].get("heavy_order")
        assert order_delivery_time is None, "Heavy order should not be delivered"

        order = controller.state_manager.get_order("heavy_order")
        assert order.status != OrderStatus.DELIVERED, "Heavy order should not be delivered"

        payment_events = controller.event_manager.get_events(EventType.PAYMENT_SENT)
        assert len(payment_events) == 0, "No payment should be sent for undelivered order"

        courier = controller.state_manager.couriers["cour_1"]
        assert courier.status == "idle", "Courier should be idle after route"

    finally:
        Path(temp_path).unlink(missing_ok=True)

def test_order_not_ready():
    """Order is not ready before start"""
    # for future
    pass