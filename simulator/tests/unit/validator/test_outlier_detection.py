"""Tests for _check_outliers.

Covers: ValidationIssueType.OUTLIER_HOP_DISTANCE
  - too few hops -> check is skipped entirely (min_hops_for_outlier_check)
  - uniform hop distances -> no outliers (zero stdev short-circuits)
  - one hop far beyond mean + N*stdev -> flagged as a warning
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


def _route_from_hop_steps(route_id, hop_steps_deg, courier_type, base_lat=55.0, base_lon=48.0):
    """Builds a route whose consecutive hops (start->s1, s1->s2, ..., sN->end)
    each advance longitude by the corresponding entry in `hop_steps_deg`, so
    the test can dictate the exact hop-distance sequence the outlier check
    will see - including the very first and very last hop."""
    lon = base_lon
    t = BASE_TIME
    wh = make_location(base_lat, lon)
    stops = []
    # last element of hop_steps_deg is consumed by the end_location, not a stop
    for i, d in enumerate(hop_steps_deg[:-1]):
        lon += d
        t = t + minutes(30)
        loc = make_location(base_lat, lon)
        stops.append(make_stop(f"ORD{i + 1}", loc, StopType.DELIVERY, i + 1, arrival=t))
    lon += hop_steps_deg[-1]
    end_location = make_location(base_lat, lon)
    return make_route(route_id, "C1", wh, end_location, BASE_TIME, stops)


def test_route_with_too_few_hops_skips_outlier_check(fake_resolver):
    # 3 hops total, below the default minimum of 4 hops required to run the
    # outlier check at all.
    route = _route_from_hop_steps("R1", [0.01, 0.01, 0.01], make_courier_type(speed_kmh=200.0))
    validator = build_validator(
        [make_courier("C1")], [make_courier_type(speed_kmh=200.0)], [route], fake_resolver,
    )
    report = validator.validate_route(route)
    assert not any(i.issue_type == ValidationIssueType.OUTLIER_HOP_DISTANCE for i in report.issues)


def test_uniform_hop_distances_raise_no_outliers(fake_resolver):
    # 6 equal hops -> stdev is zero -> the check short-circuits with no flags.
    route = _route_from_hop_steps("R2", [0.01] * 6, make_courier_type(speed_kmh=200.0))
    validator = build_validator(
        [make_courier("C1")], [make_courier_type(speed_kmh=200.0)], [route], fake_resolver,
    )
    report = validator.validate_route(route)
    assert not any(i.issue_type == ValidationIssueType.OUTLIER_HOP_DISTANCE for i in report.issues)


def test_single_far_outlier_hop_is_flagged(fake_resolver):
    # Ten small, equal hops, then one gigantic one. Enough small hops are
    # needed for a single outlier not to dominate (and hide within) its own
    # standard deviation.
    route = _route_from_hop_steps(
        "R3", [0.01] * 10 + [2.0], make_courier_type(speed_kmh=100000.0),
    )
    validator = build_validator(
        [make_courier("C1")], [make_courier_type(speed_kmh=100000.0)], [route], fake_resolver,
    )
    report = validator.validate_route(route)
    outliers = [i for i in report.issues if i.issue_type == ValidationIssueType.OUTLIER_HOP_DISTANCE]
    assert len(outliers) == 1
    assert outliers[0].severity == ValidationSeverity.WARNING


def test_outlier_threshold_respects_configured_std_multiplier(fake_resolver):
    route = _route_from_hop_steps(
        "R4", [0.01, 0.01, 0.01, 0.01, 0.03], make_courier_type(speed_kmh=100000.0),
    )

    lenient = build_validator(
        [make_courier("C1")], [make_courier_type(speed_kmh=100000.0)], [route], fake_resolver,
        config=ValidationConfig(outlier_std_multiplier=5.0),
    )
    assert not any(
        i.issue_type == ValidationIssueType.OUTLIER_HOP_DISTANCE
        for i in lenient.validate_route(route).issues
    )

    strict = build_validator(
        [make_courier("C1")], [make_courier_type(speed_kmh=100000.0)], [route], fake_resolver,
        config=ValidationConfig(outlier_std_multiplier=0.5),
    )
    assert any(
        i.issue_type == ValidationIssueType.OUTLIER_HOP_DISTANCE
        for i in strict.validate_route(route).issues
    )
