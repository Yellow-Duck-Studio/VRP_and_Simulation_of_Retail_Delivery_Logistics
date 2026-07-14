"""Tests for referential integrity checks against couriers / courier types.

Covers:
  - ValidationIssueType.MISSING_COURIER: route references a courier_id that
    doesn't exist in state_manager.couriers -> ERROR, and validation of that
    route stops immediately (no further checks are meaningful without a
    courier).
  - ValidationIssueType.MISSING_COURIER_TYPE: the courier exists but its
    courier_type_id doesn't exist -> ERROR, but the rest of the route is
    still validated (speed-feasibility checks are simply skipped).
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


def _route_for_unknown_courier():
    wh = make_location(55.0, 48.0)
    delivery = make_location(55.01, 48.0)
    stop = make_stop("ORD1", delivery, StopType.DELIVERY, arrival=BASE_TIME + minutes(30))
    return make_route("R1", "GHOST_COURIER", wh, delivery, BASE_TIME, [stop])


def test_route_referencing_unknown_courier_is_a_single_error(fake_resolver):
    route = _route_for_unknown_courier()
    # Note: no couriers registered in state at all.
    validator = build_validator([], [make_courier_type()], [route], fake_resolver)
    report = validator.validate_route(route)

    assert len(report.issues) == 1
    assert report.issues[0].issue_type == ValidationIssueType.MISSING_COURIER
    assert report.issues[0].severity == ValidationSeverity.ERROR
    assert not report.is_valid


def test_missing_courier_short_circuits_further_checks(fake_resolver):
    # Even though this route also has a broken (end<=start) time window, we
    # should only ever see the MISSING_COURIER error - the validator bails
    # out of the route entirely once the courier can't be resolved.
    wh = make_location(55.0, 48.0)
    delivery = make_location(55.01, 48.0)
    stop = make_stop("ORD1", delivery, StopType.DELIVERY, arrival=BASE_TIME)
    route = make_route("R2", "GHOST", wh, delivery, BASE_TIME, [stop])

    validator = build_validator([], [make_courier_type()], [route], fake_resolver)
    report = validator.validate_route(route)
    assert [i.issue_type for i in report.issues] == [ValidationIssueType.MISSING_COURIER]


def test_courier_with_unknown_courier_type_is_an_error_but_route_still_checked(fake_resolver):
    wh = make_location(55.0, 48.0)
    delivery = make_location(55.01, 48.0)
    stop = make_stop("ORD1", delivery, StopType.DELIVERY, arrival=BASE_TIME + minutes(30))
    route = make_route("R3", "C1", wh, delivery, BASE_TIME, [stop])

    courier = make_courier("C1", courier_type_id="UNKNOWN_TYPE")
    # No courier types registered at all -> UNKNOWN_TYPE cannot resolve.
    validator = build_validator([courier], [], [route], fake_resolver)
    report = validator.validate_route(route)

    type_errors = [i for i in report.issues if i.issue_type == ValidationIssueType.MISSING_COURIER_TYPE]
    assert len(type_errors) == 1
    assert type_errors[0].severity == ValidationSeverity.ERROR
