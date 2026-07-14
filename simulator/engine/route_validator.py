""" Trip Connection Validation for the VRP simulator. """

from __future__ import annotations

from datetime import datetime
from math import radians, sin, cos, sqrt, atan2
from statistics import mean
from typing import Dict, List, Optional, Tuple
from simulator.config.validator import ValidationConfig, ValidationReport, ValidationIssue, ValidationSeverity, ValidationIssueType

from ..schemas import Route, RouteStop, Location
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

        # Check for duplicate stops (same order_id + stop_type appearing more than once)
        # Pickup and delivery for the same order are valid (different stop_types)
        seen_stops = set()
        for idx, stop in enumerate(route.stops):
            stop_key = (stop.order_id, stop.stop_type)
            if stop_key in seen_stops:
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR, ValidationIssueType.DUPLICATE_STOP,
                    route.route_id, f"Duplicate {stop.stop_type.value} stop for order {stop.order_id} "
                                     f"(duplicate at index {idx})",
                    {"order_id": stop.order_id, "stop_type": stop.stop_type.value, "duplicate_index": idx},
                ))
            seen_stops.add(stop_key)

        # Build full node chain: declared start -> stops... -> declared end
        chain: List[Tuple[Location, Optional[RouteStop], Optional[datetime]]] = [
            (route.start_location, None, route.start_time)]
        for stop in route.stops:
            chain.append((stop.location, stop, stop.planned_arrival_time))
        chain.append((route.end_location, None, None))

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

        return issues, hop_distances

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
        }
        if hop_distances:
            summary["hop_distance_km"] = {
                "count": len(hop_distances),
                "mean": round(mean(hop_distances), 3),
                "max": round(max(hop_distances), 3),
                "min": round(min(hop_distances), 3),
            }
        return summary