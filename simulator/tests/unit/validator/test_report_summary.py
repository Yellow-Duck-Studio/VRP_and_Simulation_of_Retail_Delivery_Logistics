"""Tests for ValidationReport.is_valid and the summary dict built by
TripConnectionValidator._build_summary via validate_all().
"""

from simulator.config.validator import ValidationIssueType, ValidationSeverity
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


def _clean_route(route_id, fake_resolver, matrix, courier_id="C1"):
    """A route with no issues at all: locations are registered with the
    fake resolver/matrix (so no MISSING_DISTANCE_ENTRY fallback happens),
    speed/time windows are generous, sequence numbers are contiguous, and
    there is exactly one pickup-free delivery stop."""
    wh = make_location(55.0, 48.0)
    delivery = make_location(55.001, 48.0)
    wh_key, delivery_key = f"WH_{route_id}", f"ORD_{route_id}"
    fake_resolver.register(wh, wh_key)
    fake_resolver.register(delivery, delivery_key)
    matrix.add(wh_key, delivery_key, 0.11)

    stop = make_stop("ORD_" + route_id, delivery, StopType.DELIVERY, 1, arrival=BASE_TIME + minutes(30))
    return make_route(route_id, courier_id, wh, delivery, BASE_TIME, [stop])


def _broken_route(route_id, courier_id="C2"):
    # Duplicate sequence number -> guaranteed SEQUENCE_GAP_OR_DUPLICATE error.
    wh = make_location(55.0, 48.0)
    delivery = make_location(55.001, 48.0)
    stop1 = make_stop("ORD_" + route_id, delivery, StopType.DELIVERY, 1, arrival=BASE_TIME)
    stop2 = make_stop("ORD_" + route_id, delivery, StopType.DELIVERY, 1, arrival=BASE_TIME + minutes(5))
    return make_route(route_id, courier_id, wh, delivery, BASE_TIME, [stop1, stop2])


def test_report_with_only_clean_routes_is_valid(fake_resolver):
    matrix = FakeDistanceMatrix()
    routes = [
        _clean_route("R1", fake_resolver, matrix),
        _clean_route("R2", fake_resolver, matrix, courier_id="C2"),
    ]
    validator = build_validator(
        [make_courier("C1"), make_courier("C2")], [make_courier_type()], routes, fake_resolver,
        matrix=matrix,
    )
    report = validator.validate_all()
    assert report.is_valid
    assert report.summary["Total Routes"] == 2
    assert report.summary["Routes With Errors"] == 0
    assert report.summary["Clean Route %"] == 100.0


def test_report_with_any_error_is_invalid_and_summarised(fake_resolver):
    matrix = FakeDistanceMatrix()
    routes = [_clean_route("R1", fake_resolver, matrix), _broken_route("R2", courier_id="C2")]
    validator = build_validator(
        [make_courier("C1"), make_courier("C2")], [make_courier_type()], routes, fake_resolver,
        matrix=matrix,
    )
    report = validator.validate_all()

    assert not report.is_valid
    assert report.summary["Total Routes"] == 2
    assert report.summary["Routes With Errors"] == 1
    assert report.summary["Clean Routes"] == 1
    assert report.summary["Issues By Severity"][ValidationSeverity.ERROR.value] >= 1
    assert (
        report.summary["Issues By Type"][ValidationIssueType.SEQUENCE_GAP_OR_DUPLICATE.value] >= 1
    )


def test_issues_for_filters_by_route_id(fake_resolver):
    matrix = FakeDistanceMatrix()
    routes = [_clean_route("R1", fake_resolver, matrix), _broken_route("R2", courier_id="C2")]
    validator = build_validator(
        [make_courier("C1"), make_courier("C2")], [make_courier_type()], routes, fake_resolver,
        matrix=matrix,
    )
    report = validator.validate_all()
    assert report.issues_for("R1") == []
    r2_issues = report.issues_for("R2")
    assert len(r2_issues) >= 1
    assert all(i.route_id == "R2" for i in r2_issues)
    assert any(i.issue_type == ValidationIssueType.SEQUENCE_GAP_OR_DUPLICATE for i in r2_issues)


def test_summary_includes_issues_by_type(fake_resolver):
    # Simply verify that the summary includes Issues By Type dict
    matrix = FakeDistanceMatrix()
    routes = [_clean_route("R1", fake_resolver, matrix)]
    validator = build_validator(
        [make_courier("C1")], [make_courier_type()], routes, fake_resolver, matrix=matrix,
    )
    report = validator.validate_all()
    assert "Issues By Type" in report.summary
    assert isinstance(report.summary["Issues By Type"], dict)


def test_report_to_dict_round_trips_key_fields(fake_resolver):
    routes = [_broken_route("R1")]
    validator = build_validator(
        [make_courier("C2")], [make_courier_type()], routes, fake_resolver,
    )
    report = validator.validate_all()
    as_dict = report.to_dict()
    assert as_dict["is_valid"] is False
    assert as_dict["summary"] == report.summary
    assert len(as_dict["issues"]) == len(report.issues)
    assert as_dict["issues"][0]["route_id"] == "R1"
