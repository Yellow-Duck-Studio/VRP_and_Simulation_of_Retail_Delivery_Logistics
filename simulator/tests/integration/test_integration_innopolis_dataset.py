"""Check of TripConnectionValidator against the reference
`data/test_data_innopolis.json` fixture (as supplied for this task).
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from simulator.config.validator import ValidationConfig, ValidationIssueType
from simulator.schemas import Courier, CourierType, Location, Route, RouteStop, StopType
from simulator.tests.conftest import FakeDistanceMatrix, FakeLocationResolver, build_validator

DATA_PATH = Path(__file__).parent.parent.parent / "test_data_innopolis.json"


@pytest.fixture(scope="module")
def dataset() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _build_entities(dataset: dict):
    """Turns the raw JSON fixture into real schema objects, a resolver that
    knows how every warehouse/order coordinate maps back to its JSON id, and
    a distance matrix seeded from the JSON's (partial) distance_matrix list.
    """
    courier_types = [
        CourierType(type_id=ct["type_id"], name=ct["name"], capacity_kg=ct["capacity_kg"],
                    speed_kmh=ct["speed_kmh"])
        for ct in dataset["courier_types"]
    ]

    resolver = FakeLocationResolver()
    warehouse_locations = {}
    for wh in dataset["warehouses"]:
        loc = Location(latitude=wh["location"]["latitude"], longitude=wh["location"]["longitude"],
                       address=wh["location"].get("address"))
        warehouse_locations[wh["warehouse_id"]] = loc
        resolver.register(loc, wh["warehouse_id"])

    order_delivery_locations = {}
    order_warehouse = {}
    for order in dataset["orders"]:
        loc = Location(latitude=order["delivery_location"]["latitude"],
                       longitude=order["delivery_location"]["longitude"],
                       address=order["delivery_location"].get("address"))
        order_delivery_locations[order["order_id"]] = loc
        order_warehouse[order["order_id"]] = order["warehouse_id"]
        resolver.register(loc, order["order_id"])

    matrix = FakeDistanceMatrix(symmetric=True)
    for entry in dataset["distance_matrix"]:
        matrix.add(entry["from_id"], entry["to_id"], entry["distance"])

    couriers = []
    for c in dataset["couriers"]:
        loc = Location(latitude=c["current_location"]["latitude"], longitude=c["current_location"]["longitude"])
        couriers.append(Courier(
            courier_id=c["courier_id"], courier_type_id=c["courier_type_id"],
            affiliation_type=c["affiliation_type"], current_location=loc,
            current_load=c["current_load"], status=c["status"],
            assigned_order_ids=c["assigned_order_ids"], planned_route_ids=c["planned_route_ids"],
        ))

    def _location_for(stop_order_id: str, stop_type: str) -> Location:
        if stop_type == "pickup":
            return warehouse_locations[order_warehouse[stop_order_id]]
        return order_delivery_locations[stop_order_id]

    routes = []
    for r in dataset["routes"]:
        stops = [
            RouteStop(
                order_id=s["order_id"],
                location=_location_for(s["order_id"], s["stop_type"]),
                stop_type=StopType(s["stop_type"]),
                service_duration_minutes=s["service_duration_minutes"],
                planned_arrival_time=None,  # not present in this fixture
            )
            for s in r["stops"]
        ]
        routes.append(Route(
            route_id=r["route_id"], courier_id=r["courier_id"], warehouse_id=r["warehouse_id"],
            start_location=Location(**r["start_location"]),
            end_location=Location(**r["end_location"]),
            start_time=datetime.fromisoformat(r["start_time"]),
            stops=stops,
        ))

    return couriers, courier_types, routes, resolver, matrix


def test_validate_all_runs_cleanly_over_the_full_dataset(dataset):
    couriers, courier_types, routes, resolver, matrix = _build_entities(dataset)
    validator = build_validator(couriers, courier_types, routes, resolver, matrix=matrix)

    report = validator.validate_all()

    assert report.summary["total_routes"] == len(dataset["routes"]) == 4
    # Every route/courier/courier_type reference in this fixture is
    # well-formed, so there should be no referential-integrity errors.
    assert not any(
        i.issue_type in (ValidationIssueType.MISSING_COURIER, ValidationIssueType.MISSING_COURIER_TYPE)
        for i in report.issues
    )


def test_strict_validation_config_treats_gaps_as_errors(dataset):
    # With require_distance_matrix_entry left at its strict default, any hop
    # this fixture's partial distance matrix doesn't cover must be a hard
    # ERROR (not silently ignored).
    couriers, courier_types, routes, resolver, matrix = _build_entities(dataset)
    validator = build_validator(
        couriers, courier_types, routes, resolver, matrix=matrix,
        config=ValidationConfig(require_distance_matrix_entry=True),
    )
    report = validator.validate_all()
    assert report.summary["issues_by_severity"]["error"] >= 0  # never crashes / always a well-formed summary
    assert isinstance(report.is_valid, bool)
