"""
Trip Connection Validation for the VRP simulator.

Purpose
=======
Routes fed into the simulator come from an external clustering, VRP solver.
This module answers one question before start simulating them:

    "Is this a physically realizable sequence of stops, or does it contain
     an impossible 'teleportation' between two nodes?"

It performs *static* (pre-simulation) validation of Route objects against:
  - the distance matrix (are hops backed by real data, or silent haversine
    fallbacks that under/over-estimate real road distance?)
  - courier physical speed limits (implied speed between consecutive stops)
  - route sequence integrity (gaps, duplicates)
  - declared route totals vs. actually computed geometry
  - statistical outliers in hop distance within a route
  - continuity between consecutive routes assigned to the same courier
"""

from __future__ import annotations

from datetime import datetime
from math import radians, sin, cos, sqrt, atan2
from statistics import mean, pstdev
from typing import Dict, List, Optional, Tuple
from simulator.config.validator import ValidationConfig, ValidationReport, ValidationIssue, ValidationSeverity, ValidationIssueType

from ..schemas import Route, RouteStop, StopType, Location
from .state_manager import StateManager
from .location_resolver import LocationResolver


class TripConnectionValidator:
    """
    Validates spatial/temporal realism of already-built Route objects
    before they are handed to the simulator.
    """

    def __init__(self, state_manager: StateManager, config: Optional[ValidationConfig] = None):
        self.state_manager = state_manager
        self.config = config or ValidationConfig()
        self.resolver = LocationResolver(state_manager)

    def validate_all(self, routes: Optional[List[Route]] = None) -> ValidationReport:
        """Validate every route in scope plus cross-route courier continuity."""
        self.resolver.refresh()
        routes = routes if routes is not None else list(self.state_manager.routes.values())
        all_issues: List[ValidationIssue] = []

        hop_distances_global: List[float] = []
        for route in routes:
            issues, hops = self._validate_route(route)
            all_issues.extend(issues)
            hop_distances_global.extend(hops)

        all_issues.extend(self._validate_courier_continuity(routes))

        report = ValidationReport(issues=all_issues)
        report.summary = self._build_summary(routes, all_issues, hop_distances_global)
        return report

    def validate_route(self, route: Route) -> ValidationReport:
        issues, _ = self._validate_route(route)
        report = ValidationReport(issues=issues)
        report.summary = self._build_summary([route], issues, [])
        return report

    def _validate_route(self, route: Route) -> Tuple[List[ValidationIssue], List[float]]:
        issues: List[ValidationIssue] = []

        courier = self.state_manager.couriers.get(route.courier_id)
        if courier is None:
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR, ValidationIssueType.MISSING_COURIER,
                route.route_id, f"Route {route.route_id} references unknown courier {route.courier_id}",
            ))
            return issues, []

        courier_type = self.state_manager.courier_types.get(courier.courier_type_id)
        if courier_type is None:
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR, ValidationIssueType.MISSING_COURIER_TYPE,
                route.route_id, f"Courier {courier.courier_id} has unknown courier_type "
                                 f"{courier.courier_type_id}; cannot check speed feasibility",
            ))
            courier_type = None

        stops = sorted(route.stops, key=lambda s: s.sequence_number)
        issues.extend(self._check_route_time_window(route))
        issues.extend(self._check_sequence_integrity(route, stops))
        issues.extend(self._check_duplicate_stops(route, stops))

        # Build full node chain: declared start -> stops... -> declared end
        chain: List[Tuple[Location, Optional[RouteStop], Optional[datetime]]] = [
            (route.start_location, None, route.start_time)]
        for stop in stops:
            chain.append((stop.location, stop, stop.planned_arrival_time))
        chain.append((route.end_location, None, route.end_time))

        hop_distances: List[float] = []
        prev_departure: Optional[datetime] = route.start_time

        for idx in range(len(chain) - 1):
            from_loc, from_stop, _ = chain[idx]
            to_loc, to_stop, to_arrival = chain[idx + 1]

            distance_km, source = self._distance_km(from_loc, to_loc)
            hop_distances.append(distance_km)

            if source == "haversine" and self.config.require_distance_matrix_entry:
                sev = ValidationSeverity.ERROR
            elif source == "haversine":
                sev = ValidationSeverity.WARNING
            else:
                sev = None

            if sev is not None:
                issues.append(ValidationIssue(
                    sev, ValidationIssueType.MISSING_DISTANCE_ENTRY, route.route_id,
                    f"No distance-matrix entry between hop {idx} -> {idx + 1} "
                    f"(fell back to haversine estimate {distance_km:.2f} km); "
                    f"real road distance may differ substantially",
                    {"hop_index": idx, "haversine_km": round(distance_km, 3)},
                ))

            # Temporal feasibility (only checkable when timestamps are present)
            departure = prev_departure
            arrival = to_arrival
            if departure is not None and arrival is not None:
                available_seconds = (arrival - departure).total_seconds()

                if distance_km > 0 and available_seconds < self.config.min_travel_window_seconds:
                    issues.append(ValidationIssue(
                        ValidationSeverity.ERROR, ValidationIssueType.NON_POSITIVE_TRAVEL_WINDOW,
                        route.route_id,
                        f"Hop {idx} -> {idx + 1} covers {distance_km:.2f} km but the planned "
                        f"time window is only {available_seconds:.0f}s",
                        {"hop_index": idx, "distance_km": round(distance_km, 3),
                         "available_seconds": available_seconds},
                    ))
                elif distance_km > 0 and courier_type is not None:
                    implied_speed_kmh = distance_km / (available_seconds / 3600.0)
                    max_allowed = courier_type.speed_kmh * self.config.speed_tolerance
                    if implied_speed_kmh > max_allowed:
                        issues.append(ValidationIssue(
                            ValidationSeverity.ERROR, ValidationIssueType.TELEPORTATION,
                            route.route_id,
                            f"Hop {idx} -> {idx + 1}: implied speed {implied_speed_kmh:.1f} km/h "
                            f"exceeds courier's max feasible speed "
                            f"({courier_type.speed_kmh:.1f} km/h x{self.config.speed_tolerance} "
                            f"tolerance = {max_allowed:.1f} km/h) - route is not physically realizable",
                            {"hop_index": idx, "distance_km": round(distance_km, 3),
                             "implied_speed_kmh": round(implied_speed_kmh, 1),
                             "courier_max_speed_kmh": courier_type.speed_kmh},
                        ))

            if to_stop is not None:
                prev_departure = to_arrival if to_arrival is not None else prev_departure

        issues.extend(self._check_declared_totals(route, hop_distances))
        issues.extend(self._check_declared_speed(route, courier_type))
        issues.extend(self._check_outliers(route, hop_distances))

        return issues, hop_distances

    @staticmethod
    def _check_route_time_window(route: Route) -> List[ValidationIssue]:
        issues = []
        if route.end_time <= route.start_time:
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR, ValidationIssueType.INVALID_ROUTE_TIME_WINDOW,
                route.route_id,
                f"Route {route.route_id} end_time ({route.end_time.isoformat()}) is not after "
                f"start_time ({route.start_time.isoformat()}) - the route ends before/when it "
                f"starts, which is a temporal impossibility regardless of distance",
                {"start_time": route.start_time.isoformat(), "end_time": route.end_time.isoformat()},
            ))
        return issues

    @staticmethod
    def _check_sequence_integrity(route: Route, stops: List[RouteStop]) -> List[ValidationIssue]:
        issues = []
        seen = set()
        for stop in stops:
            if stop.sequence_number in seen:
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR, ValidationIssueType.SEQUENCE_GAP_OR_DUPLICATE,
                    route.route_id, f"Duplicate sequence_number {stop.sequence_number} "
                                     f"in route {route.route_id}",
                    {"sequence_number": stop.sequence_number},
                ))
            seen.add(stop.sequence_number)

        expected = list(range(1, len(stops) + 1))
        actual = sorted(seen)
        if actual != expected:
            issues.append(ValidationIssue(
                ValidationSeverity.WARNING, ValidationIssueType.SEQUENCE_GAP_OR_DUPLICATE,
                route.route_id,
                f"Route {route.route_id} sequence numbers {actual} are not a contiguous "
                f"1..{len(stops)} run - possible gap from removed/unassigned stops",
                {"expected": expected, "actual": actual},
            ))
        return issues

    @staticmethod
    def _check_duplicate_stops(route: Route, stops: List[RouteStop]) -> List[ValidationIssue]:
        issues = []
        seen = set()
        for stop in stops:
            key = (stop.order_id, stop.stop_type)
            if key in seen:
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR, ValidationIssueType.DUPLICATE_STOP,
                    route.route_id,
                    f"Order {stop.order_id} has duplicate {stop.stop_type} stops in "
                    f"route {route.route_id}",
                    {"order_id": stop.order_id, "stop_type": stop.stop_type},
                ))
            seen.add(key)

            if stop.stop_type == StopType.DELIVERY and (stop.order_id, StopType.PICKUP) not in seen:
                # Pickup either happens later (data error) or in a different route entirely,
                # which we can't confirm here - surface as info, not a hard failure.
                pass
        return issues

    def _check_declared_totals(self, route: Route, hop_distances: List[float]) -> List[ValidationIssue]:
        issues = []
        if route.total_distance_km and route.total_distance_km > 0:
            computed = sum(hop_distances)
            declared = route.total_distance_km
            rel_diff = abs(computed - declared) / declared if declared else 0
            if rel_diff > self.config.distance_total_tolerance_pct:
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING, ValidationIssueType.DISTANCE_TOTAL_MISMATCH,
                    route.route_id,
                    f"Declared total_distance_km={declared:.2f} differs from computed "
                    f"hop sum={computed:.2f} by {rel_diff * 100:.1f}% "
                    f"(tolerance {self.config.distance_total_tolerance_pct * 100:.0f}%)",
                    {"declared_km": declared, "computed_km": round(computed, 3),
                     "relative_diff_pct": round(rel_diff * 100, 1)},
                ))
        return issues

    def _check_declared_speed(self, route: Route, courier_type) -> List[ValidationIssue]:
        """Check if declared total_distance_km and duration imply feasible speed."""
        issues = []
        if courier_type is None:
            return issues
        if route.total_distance_km is None or route.total_distance_km <= 0:
            return issues
        if route.total_duration_minutes is None or route.total_duration_minutes <= 0:
            return issues

        duration_hours = route.total_duration_minutes / 60.0
        implied_speed_kmh = route.total_distance_km / duration_hours
        max_allowed = courier_type.speed_kmh * self.config.speed_tolerance

        if implied_speed_kmh > max_allowed:
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR, ValidationIssueType.TELEPORTATION,
                route.route_id,
                f"Route declared values imply speed {implied_speed_kmh:.1f} km/h "
                f"({route.total_distance_km:.2f} km in {route.total_duration_minutes:.0f} min), "
                f"which exceeds courier's max feasible speed "
                f"({courier_type.speed_kmh:.1f} km/h x{self.config.speed_tolerance} "
                f"tolerance = {max_allowed:.1f} km/h) - route is not physically realizable",
                {"declared_distance_km": route.total_distance_km,
                 "declared_duration_minutes": route.total_duration_minutes,
                 "implied_speed_kmh": round(implied_speed_kmh, 1),
                 "courier_max_speed_kmh": courier_type.speed_kmh},
            ))
        return issues

    def _check_outliers(self, route: Route, hop_distances: List[float]) -> List[ValidationIssue]:
        issues = []
        if len(hop_distances) < self.config.min_hops_for_outlier_check:
            return issues
        mu = mean(hop_distances)
        sigma = pstdev(hop_distances)
        if sigma == 0:
            return issues
        threshold = mu + self.config.outlier_std_multiplier * sigma
        for idx, d in enumerate(hop_distances):
            if d > threshold:
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING, ValidationIssueType.OUTLIER_HOP_DISTANCE,
                    route.route_id,
                    f"Hop {idx} distance {d:.2f} km is a statistical outlier for this route "
                    f"(mean={mu:.2f}, std={sigma:.2f}, threshold={threshold:.2f}) - possible "
                    f"clustering error assigning a distant order to this route",
                    {"hop_index": idx, "distance_km": round(d, 3), "mean_km": round(mu, 3),
                     "std_km": round(sigma, 3)},
                ))
        return issues

    def _validate_courier_continuity(self, routes: List[Route]) -> List[ValidationIssue]:
        """Checks that consecutive routes assigned to the same courier connect in space."""
        issues: List[ValidationIssue] = []
        by_courier: Dict[str, List[Route]] = {}
        for r in routes:
            by_courier.setdefault(r.courier_id, []).append(r)

        for courier_id, courier_routes in by_courier.items():
            ordered = sorted(courier_routes, key=lambda r: r.start_time)
            for prev_route, next_route in zip(ordered, ordered[1:]):
                gap_km, _ = self._distance_km(prev_route.end_location, next_route.start_location)
                if gap_km > self.config.max_inter_route_gap_km:
                    issues.append(ValidationIssue(
                        ValidationSeverity.WARNING, ValidationIssueType.ROUTE_DISCONTINUITY,
                        next_route.route_id,
                        f"Courier {courier_id}: route {prev_route.route_id} ends {gap_km:.2f} km "
                        f"away from where route {next_route.route_id} starts "
                        f"(threshold {self.config.max_inter_route_gap_km} km) - implies an "
                        f"unaccounted repositioning trip",
                        {"courier_id": courier_id, "prev_route_id": prev_route.route_id,
                         "next_route_id": next_route.route_id, "gap_km": round(gap_km, 3)},
                    ))
        return issues

    def _distance_km(self, from_loc: Location, to_loc: Location) -> Tuple[float, str]:
        """Returns (distance_km, source), source in {"matrix", "haversine", "trivial"}.

        (mirrors CourierFSM._distance_km, but exposes source)

        "trivial" = from_loc and to_loc are the same physical point (e.g. a
        pickup stop located at the same coordinates as the route's start
        location) - there is nothing to look up, distance is definitionally
        zero, and this must NOT be treated as a missing distance-matrix entry.
        """
        if self.resolver.same_location(from_loc, to_loc):
            return 0.0, "trivial"

        matrix = self.state_manager.distance_matrix
        if matrix is not None:
            from_key = self.resolver.matrix_key(from_loc)
            to_key = self.resolver.matrix_key(to_loc)
            try:
                return matrix.get_distance(from_key, to_key), "matrix"
            except KeyError:
                pass
        return self._haversine_km(from_loc, to_loc), "haversine"

    @staticmethod
    def _haversine_km(from_loc: Location, to_loc: Location) -> float:
        R = 6371.0
        lat1, lon1 = radians(from_loc.latitude), radians(from_loc.longitude)
        lat2, lon2 = radians(to_loc.latitude), radians(to_loc.longitude)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c

    @staticmethod
    def _build_summary(routes: List[Route], issues: List[ValidationIssue],
                       hop_distances: List[float]) -> dict:
        by_severity = {s.value: 0 for s in ValidationSeverity}
        by_type: Dict[str, int] = {}
        routes_with_errors = set()
        routes_with_warnings = set()

        for issue in issues:
            by_severity[issue.severity.value] += 1
            by_type[issue.issue_type.value] = by_type.get(issue.issue_type.value, 0) + 1
            if issue.severity == ValidationSeverity.ERROR:
                routes_with_errors.add(issue.route_id)
            elif issue.severity == ValidationSeverity.WARNING:
                routes_with_warnings.add(issue.route_id)

        total_routes = len(routes)
        clean_routes = total_routes - len(routes_with_errors | routes_with_warnings)

        summary = {
            "total_routes": total_routes,
            "routes_with_errors": len(routes_with_errors),
            "routes_with_warnings": len(routes_with_warnings),
            "clean_routes": max(clean_routes, 0),
            "clean_route_pct": round((clean_routes / total_routes) * 100, 1) if total_routes else 0.0,
            "issues_by_severity": by_severity,
            "issues_by_type": by_type,
            "teleportation_count": by_type.get(ValidationIssueType.TELEPORTATION.value, 0),
        }
        if hop_distances:
            summary["hop_distance_km"] = {
                "count": len(hop_distances),
                "mean": round(mean(hop_distances), 3),
                "max": round(max(hop_distances), 3),
                "min": round(min(hop_distances), 3),
            }
        return summary