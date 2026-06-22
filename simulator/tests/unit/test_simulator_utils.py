import pytest
from datetime import datetime, timedelta
from simulator.engine import SimulationController, EventManager, StateManager
from simulator.fsm.courier_fsm import CourierFSM
from simulator.schemas import (
    Location, CourierType, Courier, Order, TimeWindow,
    DistanceMatrix, AffiliationType, CourierStatus
)

def test_distance_km_fallback():
    """Test distance using haversine without distance matrix"""
    state_manager = StateManager()
    courier = Courier(
        courier_id="cour_1",
        courier_type_id="car_1",
        affiliation_type=AffiliationType.SHIFT,
        current_location=Location(latitude=55.7558, longitude=37.6173)
    )
    fsm = CourierFSM(courier, state_manager, EventManager(), order_fsms={})
    from_loc = Location(latitude=55.7558, longitude=37.6173)
    to_loc = Location(latitude=55.75, longitude=37.61)
    dist = fsm._distance_km(from_loc, to_loc)
    assert 0.5 < dist < 1.0

def test_distance_km_from_matrix():
    """Test distance reading from distance matrix"""
    state_manager = StateManager()
    from_loc = Location(latitude=55.7558, longitude=37.6173)
    to_loc = Location(latitude=55.75, longitude=37.61)
    key_from = f"{from_loc.latitude},{from_loc.longitude}"
    key_to = f"{to_loc.latitude},{to_loc.longitude}"
    matrix = DistanceMatrix.from_dict({(key_from, key_to): 2.5})
    state_manager.set_distance_matrix(matrix)

    courier = Courier(
        courier_id="cour_1",
        courier_type_id="car_1",
        affiliation_type=AffiliationType.SHIFT,
        current_location=from_loc
    )
    fsm = CourierFSM(courier, state_manager, EventManager(), order_fsms={})
    dist = fsm._distance_km(from_loc, to_loc)
    assert dist == 2.5

def test_travel_time_seconds():
    """Test travel time calculation"""
    state_manager = StateManager()
    courier_type = CourierType(type_id="car_1", name="Car", capacity_kg=100, speed_kmh=60)
    state_manager.add_courier_type(courier_type)

    courier = Courier(
        courier_id="cour_1",
        courier_type_id="car_1",
        affiliation_type=AffiliationType.SHIFT,
        current_location=Location(latitude=55.7558, longitude=37.6173)
    )
    from_loc = Location(latitude=55.7558, longitude=37.6173)
    to_loc = Location(latitude=55.75, longitude=37.61)
    fsm = CourierFSM(courier, state_manager, EventManager(), order_fsms={})
    seconds = fsm._travel_time(from_loc, to_loc)
    # ~0.6 km at 60 km/h -> ~36 sec
    assert 30 < seconds < 50

def test_add_payment():
    """Test payment calculation and state update (without event publishing)"""
    state_manager = StateManager()
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
    state_manager.delivery_results[order.order_id] = {"sla_met": False}

    fsm = CourierFSM(courier, state_manager, EventManager(), order_fsms={})
    fsm._add_payment(distance_km=2.5, order=order, in_window=False, current_time=datetime.now())

    assert state_manager.courier_payments["cour_1"] == 125.0  # 2.5*50

    state_manager.courier_payments.clear()
    fsm._add_payment(distance_km=2.5, order=order, in_window=True, current_time=datetime.now())
    assert state_manager.courier_payments["cour_1"] == 225.0  # (2.5*50 + 100)