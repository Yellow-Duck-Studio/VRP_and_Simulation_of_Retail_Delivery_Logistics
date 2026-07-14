import pytest
import json
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from simulator.config.validator import ValidationConfig
from simulator.engine.route_validator import TripConnectionValidator
from simulator.engine.state_manager import StateManager
from simulator.schemas import Courier, CourierType, Location, Route, RouteStop, StopType, AffiliationType

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
                "delivery_time_window_end": (now + timedelta(minutes=60)).isoformat(),
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
                "stops": [
                    {
                        "order_id": "ord_1",
                        "location": {"latitude": 55.7558, "longitude": 37.6173},
                        "stop_type": "pickup",
                        "service_duration_minutes": 5
                    },
                    {
                        "order_id": "ord_1",
                        "location": {"latitude": 55.75, "longitude": 37.61},
                        "stop_type": "delivery",
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
    yield temp_path
    import os
    os.unlink(temp_path)


BASE_TIME = datetime(2024, 6, 17, 9, 0, 0)


def make_location(lat: float, lon: float, address: Optional[str] = None) -> Location:
    return Location(latitude=lat, longitude=lon, address=address)


def make_stop(
    order_id: str,
    location: Location,
    stop_type: StopType,
    arrival: Optional[datetime] = None,
    service_duration_minutes: float = 5.0,
) -> RouteStop:
    return RouteStop(
        order_id=order_id,
        location=location,
        stop_type=stop_type,
        service_duration_minutes=service_duration_minutes,
        planned_arrival_time=arrival,
    )


def make_route(
    route_id: str,
    courier_id: str,
    start_location: Location,
    end_location: Location,
    start_time: datetime,
    stops: List[RouteStop],
    warehouse_id: str = "WH_TEST",
) -> Route:
    return Route(
        route_id=route_id,
        courier_id=courier_id,
        warehouse_id=warehouse_id,
        start_location=start_location,
        end_location=end_location,
        start_time=start_time,
        stops=stops,
    )


def make_courier_type(type_id: str = "car", speed_kmh: float = 40.0, capacity_kg: float = 100.0) -> CourierType:
    return CourierType(type_id=type_id, name=type_id, capacity_kg=capacity_kg, speed_kmh=speed_kmh)


def make_courier(
    courier_id: str,
    courier_type_id: str = "car",
    affiliation_type: AffiliationType = AffiliationType("shift"),
    current_location: Optional[Location] = None,
) -> Courier:
    return Courier(
        courier_id=courier_id,
        courier_type_id=courier_type_id,
        affiliation_type=affiliation_type,
        current_location=current_location or make_location(0.0, 0.0),
    )


class FakeDistanceMatrix:
    """Dict-backed stand-in for the real distance matrix."""

    def __init__(self, symmetric: bool = True):
        self._data: Dict[Tuple[str, str], float] = {}
        self._symmetric = symmetric

    def add(self, from_key: str, to_key: str, distance_km: float) -> "FakeDistanceMatrix":
        self._data[(from_key, to_key)] = distance_km
        if self._symmetric:
            self._data[(to_key, from_key)] = distance_km
        return self

    def get_distance(self, from_key: str, to_key: str) -> float:
        return self._data[(from_key, to_key)]


class FakeLocationResolver:
    """Fully test-controlled stand-in for the real LocationResolver."""

    def __init__(self):
        self._keys: Dict[Tuple[float, float], str] = {}
        self.refresh_calls = 0

    def register(self, location: Location, key: str) -> "FakeLocationResolver":
        self._keys[(location.latitude, location.longitude)] = key
        return self

    def refresh(self) -> None:
        self.refresh_calls += 1

    def same_location(self, a: Location, b: Location) -> bool:
        return (a.latitude, a.longitude) == (b.latitude, b.longitude)

    def matrix_key(self, location: Location) -> str:
        coord = (location.latitude, location.longitude)
        if coord in self._keys:
            return self._keys[coord]

        return f"unregistered:{coord[0]}:{coord[1]}"


@pytest.fixture
def default_config() -> ValidationConfig:
    return ValidationConfig()


@pytest.fixture
def fake_resolver() -> FakeLocationResolver:
    return FakeLocationResolver()


@pytest.fixture
def fake_matrix() -> FakeDistanceMatrix:
    return FakeDistanceMatrix()


def build_validator(
    couriers: List[Courier],
    courier_types: List[CourierType],
    routes: List[Route],
    resolver: FakeLocationResolver,
    matrix: Optional[FakeDistanceMatrix] = None,
    config: Optional[ValidationConfig] = None,
) -> TripConnectionValidator:

    state_manager = StateManager()
    for courier in couriers:
        state_manager.add_courier(courier)
    for courier_type in courier_types:
        state_manager.add_courier_type(courier_type)
    for route in routes:
        state_manager.add_route(route)
    state_manager.distance_matrix = matrix if matrix is not None else FakeDistanceMatrix()
    validator = TripConnectionValidator(state_manager, config)
    validator.resolver = resolver
    return validator


def minutes(n: float) -> timedelta:
    return timedelta(minutes=n)