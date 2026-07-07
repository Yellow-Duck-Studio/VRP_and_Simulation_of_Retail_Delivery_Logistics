"""Tests for _check_duplicate_stops.

Covers: ValidationIssueType.DUPLICATE_STOP
"""

from simulator.config.validator import ValidationIssueType, ValidationSeverity
from simulator.schemas import StopType
from simulator.tests.conftest import (
    BASE_TIME,
    build_validator,
    make_courier,
    make_courier_type,
    make_location,
    make_route,
    make_stop,
    minutes,
)


def _route_with_stops(route_id, stops):
    wh = make_location(55.0, 48.0)
    end = stops[-1].location if stops else wh
    return make_route(route_id, "C1", wh, end, BASE_TIME, stops)


def test_single_pickup_and_delivery_per_order_is_valid(fake_resolver):
    wh = make_location(55.0, 48.0)
    delivery = make_location(55.01, 48.0)
    stops = [
        make_stop("ORD1", wh, StopType.PICKUP, 1, arrival=BASE_TIME + minutes(5)),
        make_stop("ORD1", delivery, StopType.DELIVERY, 2, arrival=BASE_TIME + minutes(15)),
    ]
    route = _route_with_stops("R1", stops)
    validator = build_validator([make_courier("C1")], [make_courier_type()], [route], fake_resolver)
    report = validator.validate_route(route)
    assert not any(i.issue_type == ValidationIssueType.DUPLICATE_STOP for i in report.issues)


def test_duplicate_delivery_stop_for_same_order_is_an_error(fake_resolver):
    wh = make_location(55.0, 48.0)
    delivery = make_location(55.01, 48.0)
    stops = [
        make_stop("ORD1", wh, StopType.PICKUP, 1, arrival=BASE_TIME + minutes(5)),
        make_stop("ORD1", delivery, StopType.DELIVERY, 2, arrival=BASE_TIME + minutes(15)),
        make_stop("ORD1", delivery, StopType.DELIVERY, 3, arrival=BASE_TIME + minutes(25)),
    ]
    route = _route_with_stops("R2", stops)
    validator = build_validator([make_courier("C1")], [make_courier_type()], [route], fake_resolver)
    report = validator.validate_route(route)
    errors = [i for i in report.issues if i.issue_type == ValidationIssueType.DUPLICATE_STOP]
    assert len(errors) == 1
    assert errors[0].severity == ValidationSeverity.ERROR
    assert errors[0].details["order_id"] == "ORD1"
    assert errors[0].details["stop_type"] == StopType.DELIVERY


def test_pickup_and_delivery_for_same_order_are_not_flagged_as_duplicates(fake_resolver):
    # A pickup and a delivery for the same order share order_id but differ in
    # stop_type, so they must NOT be treated as duplicates of each other.
    wh = make_location(55.0, 48.0)
    delivery = make_location(55.01, 48.0)
    stops = [
        make_stop("ORD1", wh, StopType.PICKUP, 1, arrival=BASE_TIME + minutes(5)),
        make_stop("ORD1", delivery, StopType.DELIVERY, 2, arrival=BASE_TIME + minutes(15)),
    ]
    route = _route_with_stops("R3", stops)
    validator = build_validator([make_courier("C1")], [make_courier_type()], [route], fake_resolver)
    report = validator.validate_route(route)
    assert not any(i.issue_type == ValidationIssueType.DUPLICATE_STOP for i in report.issues)
