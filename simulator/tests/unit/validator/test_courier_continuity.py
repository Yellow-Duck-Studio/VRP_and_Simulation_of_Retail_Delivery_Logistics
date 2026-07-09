"""Tests for _validate_courier_continuity.

Covers: ValidationIssueType.ROUTE_DISCONTINUITY

This check only runs as part of validate_all() (it operates across multiple
routes for the same courier), not validate_route().
"""

from simulator.config.validator import ValidationConfig, ValidationIssueType, ValidationSeverity
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


def _route(route_id, start_loc, end_loc, start_time):
    stop = make_stop("ORD_" + route_id, end_loc, StopType.DELIVERY, 1, arrival=start_time)
    return make_route(route_id, "C1", start_loc, end_loc, start_time, [stop])


def test_back_to_back_routes_ending_where_next_starts_raise_no_discontinuity(fake_resolver):
    wh = make_location(55.0, 48.0)
    handoff = make_location(55.01, 48.0)
    r1 = _route("R1", wh, handoff, BASE_TIME)
    r2 = _route("R2", handoff, wh, BASE_TIME + minutes(40))

    validator = build_validator(
        [make_courier("C1")], [make_courier_type()], [r1, r2], fake_resolver,
    )
    report = validator.validate_all()
    assert not any(i.issue_type == ValidationIssueType.ROUTE_DISCONTINUITY for i in report.issues)


def test_gap_between_consecutive_routes_over_threshold_is_a_warning(fake_resolver):
    wh = make_location(55.0, 48.0)
    end_of_r1 = make_location(55.01, 48.0)
    start_of_r2 = make_location(56.0, 49.0)  # far away, unaccounted repositioning
    r1 = _route("R1", wh, end_of_r1, BASE_TIME)
    r2 = _route("R2", start_of_r2, wh, BASE_TIME + minutes(40))

    validator = build_validator(
        [make_courier("C1")], [make_courier_type()], [r1, r2], fake_resolver,
    )
    report = validator.validate_all()
    discontinuities = [i for i in report.issues if i.issue_type == ValidationIssueType.ROUTE_DISCONTINUITY]
    assert len(discontinuities) == 1
    assert discontinuities[0].severity == ValidationSeverity.WARNING
    assert discontinuities[0].route_id == "R2"
    assert discontinuities[0].details["prev_route_id"] == "R1"
    assert discontinuities[0].details["next_route_id"] == "R2"


def test_gap_within_configured_threshold_is_not_flagged(fake_resolver):
    wh = make_location(55.0, 48.0)
    end_of_r1 = make_location(55.01, 48.0)
    # ~1.1 km away - allowed under a widened 2km threshold.
    start_of_r2 = make_location(55.02, 48.0)
    r1 = _route("R1", wh, end_of_r1, BASE_TIME)
    r2 = _route("R2", start_of_r2, wh, BASE_TIME + minutes(40))

    validator = build_validator(
        [make_courier("C1")], [make_courier_type()], [r1, r2], fake_resolver,
        config=ValidationConfig(max_inter_route_gap_km=2.0),
    )
    report = validator.validate_all()
    assert not any(i.issue_type == ValidationIssueType.ROUTE_DISCONTINUITY for i in report.issues)


def test_routes_for_different_couriers_are_never_compared(fake_resolver):
    wh = make_location(55.0, 48.0)
    far = make_location(60.0, 60.0)
    r1 = _route("R1", wh, far, BASE_TIME)
    # Different courier entirely - the huge "gap" between R1's end and R2's
    # start must not be flagged, since they were never the same courier's
    # responsibility to bridge.
    r2 = _route("R2", wh, far, BASE_TIME + minutes(40))
    r2.courier_id = "C2"

    validator = build_validator(
        [make_courier("C1"), make_courier("C2")], [make_courier_type()], [r1, r2], fake_resolver,
    )
    report = validator.validate_all()
    assert not any(i.issue_type == ValidationIssueType.ROUTE_DISCONTINUITY for i in report.issues)
