"""Tests for _check_sequence_integrity.

Covers: ValidationIssueType.SEQUENCE_GAP_OR_DUPLICATE
  - duplicate sequence_number -> ERROR
  - non-contiguous 1..N run (gap) -> WARNING
  - normal contiguous sequence -> no issue
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


def test_contiguous_sequence_raises_no_issue(fake_resolver):
    d1 = make_location(55.01, 48.0)
    d2 = make_location(55.02, 48.0)
    stops = [
        make_stop("ORD1", d1, StopType.DELIVERY, 1, arrival=BASE_TIME + minutes(10)),
        make_stop("ORD2", d2, StopType.DELIVERY, 2, arrival=BASE_TIME + minutes(20)),
    ]
    route = _route_with_stops("R1", stops)
    validator = build_validator([make_courier("C1")], [make_courier_type()], [route], fake_resolver)
    report = validator.validate_route(route)
    assert not any(i.issue_type == ValidationIssueType.SEQUENCE_GAP_OR_DUPLICATE for i in report.issues)


def test_duplicate_sequence_number_is_an_error(fake_resolver):
    d1 = make_location(55.01, 48.0)
    d2 = make_location(55.02, 48.0)
    stops = [
        make_stop("ORD1", d1, StopType.DELIVERY, 1, arrival=BASE_TIME + minutes(10)),
        make_stop("ORD2", d2, StopType.DELIVERY, 1, arrival=BASE_TIME + minutes(20)),
    ]
    route = _route_with_stops("R2", stops)
    validator = build_validator([make_courier("C1")], [make_courier_type()], [route], fake_resolver)
    report = validator.validate_route(route)
    errors = [
        i for i in report.issues
        if i.issue_type == ValidationIssueType.SEQUENCE_GAP_OR_DUPLICATE
        and i.severity == ValidationSeverity.ERROR
    ]
    assert len(errors) == 1
    assert errors[0].details["sequence_number"] == 1


def test_sequence_gap_is_a_warning(fake_resolver):
    d1 = make_location(55.01, 48.0)
    d2 = make_location(55.02, 48.0)
    stops = [
        make_stop("ORD1", d1, StopType.DELIVERY, 1, arrival=BASE_TIME + minutes(10)),
        make_stop("ORD2", d2, StopType.DELIVERY, 3, arrival=BASE_TIME + minutes(20)),  # skips 2
    ]
    route = _route_with_stops("R3", stops)
    validator = build_validator([make_courier("C1")], [make_courier_type()], [route], fake_resolver)
    report = validator.validate_route(route)
    warnings = [
        i for i in report.issues
        if i.issue_type == ValidationIssueType.SEQUENCE_GAP_OR_DUPLICATE
        and i.severity == ValidationSeverity.WARNING
    ]
    assert len(warnings) == 1
    assert warnings[0].details["actual"] == [1, 3]
    assert warnings[0].details["expected"] == [1, 2]
