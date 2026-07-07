"""Tests for how each hop's distance is sourced.

Covers: ValidationIssueType.MISSING_DISTANCE_ENTRY
  - a hop backed by a real distance-matrix entry -> no issue
  - a hop with no matrix entry falls back to haversine:
      * ERROR when config.require_distance_matrix_entry is True (default)
      * WARNING when config.require_distance_matrix_entry is False
  - a "trivial" hop (from == to, e.g. a pickup at the warehouse where the
    route also starts) is never flagged, even though it has no matrix entry
"""

from simulator.config.validator import ValidationConfig, ValidationIssueType, ValidationSeverity
from simulator.schemas import StopType
from simulator.tests.conftest import (
    BASE_TIME,
    FakeDistanceMatrix,
    build_validator,
    make_courier,
    make_courier_type,
    make_location,
    make_route,
    make_stop,
    minutes,
)


def test_hop_backed_by_matrix_entry_raises_no_missing_distance_issue(fake_resolver):
    wh = make_location(55.0, 48.0)
    delivery = make_location(55.05, 48.05)

    fake_resolver.register(wh, "WH")
    fake_resolver.register(delivery, "ORD1")

    matrix = FakeDistanceMatrix().add("WH", "ORD1", 3.0)

    stop = make_stop("ORD1", delivery, StopType.DELIVERY, 1, arrival=BASE_TIME + minutes(20))
    route = make_route("R1", "C1", wh, delivery, BASE_TIME, [stop])

    validator = build_validator(
        [make_courier("C1")], [make_courier_type()], [route], fake_resolver, matrix=matrix,
    )
    report = validator.validate_route(route)
    assert not any(i.issue_type == ValidationIssueType.MISSING_DISTANCE_ENTRY for i in report.issues)


def test_missing_matrix_entry_is_an_error_by_default(fake_resolver):
    wh = make_location(55.0, 48.0)
    delivery = make_location(55.05, 48.05)
    # Neither location is registered in the fake resolver's key map, and the
    # matrix is empty -> guaranteed miss -> haversine fallback.
    stop = make_stop("ORD1", delivery, StopType.DELIVERY, 1, arrival=BASE_TIME + minutes(60))
    route = make_route("R2", "C1", wh, delivery, BASE_TIME, [stop])

    validator = build_validator(
        [make_courier("C1")], [make_courier_type(speed_kmh=200.0)], [route], fake_resolver,
    )
    report = validator.validate_route(route)
    missing = [i for i in report.issues if i.issue_type == ValidationIssueType.MISSING_DISTANCE_ENTRY]
    assert len(missing) >= 1
    assert all(i.severity == ValidationSeverity.ERROR for i in missing)
    assert "haversine_km" in missing[0].details


def test_missing_matrix_entry_is_only_a_warning_when_not_required(fake_resolver):
    wh = make_location(55.0, 48.0)
    delivery = make_location(55.05, 48.05)
    stop = make_stop("ORD1", delivery, StopType.DELIVERY, 1, arrival=BASE_TIME + minutes(60))
    route = make_route("R3", "C1", wh, delivery, BASE_TIME, [stop])

    config = ValidationConfig(require_distance_matrix_entry=False)
    validator = build_validator(
        [make_courier("C1")], [make_courier_type(speed_kmh=200.0)], [route], fake_resolver, config=config,
    )
    report = validator.validate_route(route)
    missing = [i for i in report.issues if i.issue_type == ValidationIssueType.MISSING_DISTANCE_ENTRY]
    assert len(missing) >= 1
    assert all(i.severity == ValidationSeverity.WARNING for i in missing)


def test_same_physical_point_hop_is_trivial_and_never_flagged(fake_resolver):
    # Pickup stop located exactly at the route's declared start_location
    # (e.g. warehouse pickup): distance is definitionally zero and must not
    # be reported as a missing distance-matrix entry, even though no matrix
    # entry could ever exist for "point to itself".
    wh = make_location(55.0, 48.0)
    delivery = make_location(55.05, 48.05)
    pickup_stop = make_stop("ORD1", wh, StopType.PICKUP, 1, arrival=BASE_TIME + minutes(5))
    delivery_stop = make_stop("ORD1", delivery, StopType.DELIVERY, 2, arrival=BASE_TIME + minutes(60))
    route = make_route(
        "R4", "C1", wh, delivery, BASE_TIME, [pickup_stop, delivery_stop],
    )

    fake_resolver.register(delivery, "ORD1")
    matrix = FakeDistanceMatrix().add("WH", "ORD1", 4.0)
    fake_resolver.register(wh, "WH")

    validator = build_validator(
        [make_courier("C1")], [make_courier_type(speed_kmh=200.0)], [route], fake_resolver, matrix=matrix,
    )
    report = validator.validate_route(route)
    missing = [i for i in report.issues if i.issue_type == ValidationIssueType.MISSING_DISTANCE_ENTRY]
    # Only the (already-registered) WH -> ORD1 hop remains, and it resolves
    # against the matrix, so there should be no missing-distance issues at all.
    assert missing == []
