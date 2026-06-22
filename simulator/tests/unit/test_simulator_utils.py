import pytest
from datetime import datetime, timedelta
from simulator.core import SimulationController
from simulator.schemas import Location, CourierType, Order, Courier, TimeWindow, Route, RouteStop, StopType, AffiliationType, CourierStatus

def test_distance_km_fallback():
    """Test distance using haversine without distance matrix"""
    controller = SimulationController(start_time=datetime.now())
    from_loc = Location(latitude=55.7558, longitude=37.6173)
    to_loc = Location(latitude=55.75, longitude=37.61)
    dist = controller._distance_km(from_loc, to_loc)

    assert 0.5 < dist < 1.0

def test_distance_km_from_matrix():
    """Test distance reading from distance matrix"""
    controller = SimulationController(start_time=datetime.now())

    from simulator.schemas import DistanceMatrix
    matrix = DistanceMatrix.from_dict({("wh_1", "ord_1"): 2.5})
    controller.state_manager.set_distance_matrix(matrix)
    from_loc = Location(latitude=55.7558, longitude=37.6173)
    to_loc = Location(latitude=55.75, longitude=37.61)

    key_from = f"{from_loc.latitude},{from_loc.longitude}"
    key_to = f"{to_loc.latitude},{to_loc.longitude}"
    matrix = DistanceMatrix.from_dict({(key_from, key_to): 2.5})
    controller.state_manager.set_distance_matrix(matrix)
    dist = controller._distance_km(from_loc, to_loc)
    assert dist == 2.5

def test_travel_time_seconds():
    """Test travel time calculation"""
    controller = SimulationController(start_time=datetime.now())

    ct = CourierType(type_id="car_1", name="Car", capacity_kg=100, speed_kmh=60)
    controller.state_manager.add_courier_type(ct)
    courier = Courier(
        courier_id="cour_1",
        courier_type_id="car_1",
        affiliation_type=AffiliationType.SHIFT,
        current_location=Location(latitude=55.7558, longitude=37.6173)
    )
    from_loc = Location(latitude=55.7558, longitude=37.6173)
    to_loc = Location(latitude=55.75, longitude=37.61)

    seconds = controller._travel_time_seconds(courier, from_loc, to_loc)

    assert 40 < seconds < 50

def test_add_payment():
    """test payment sending"""
    controller = SimulationController(start_time=datetime.now())

    courier = Courier(
        courier_id="cour_1",
        courier_type_id="car_1",
        affiliation_type=AffiliationType.SHIFT,
        current_location=Location(latitude=55.7558, longitude=37.6173)
    )
    order = Order(
        order_id="ord_1",
        warehouse_id="wh_1",
        delivery_location=Location(latitude=55.75, longitude=37.61),
        delivery_time_window=TimeWindow(start=datetime.now(), end=datetime.now()+timedelta(hours=1)),
        mass_kg=5.0,
        ready_time=datetime.now()
    )

    controller.state_manager.delivery_results[order.order_id] = {"sla_met": False}

    controller._add_payment(courier, 2.5, order)

    # When _add_payment will be changed:
    # assert controller.state_manager.courier_payment["cour_1"] == 125.0  # 2.5*50

    events = controller.event_manager.get_events()

    payment_event = None
    for ev in events:
        if ev.event_type == "payment_sent" and ev.data.get("amount"):
            payment_event = ev
    assert payment_event is not None
    assert payment_event.data["amount"] == 125.0  # 2.5*50 (без бонуса)