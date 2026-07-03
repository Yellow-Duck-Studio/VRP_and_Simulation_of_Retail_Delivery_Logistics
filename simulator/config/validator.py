from enum import Enum
from dataclasses import dataclass, field
from typing import List


class ValidationSeverity(str, Enum):
    ERROR = "error"      # physically impossible / contract-breaking -> should block a run
    WARNING = "warning"  # suspicious, likely a solver/data quality issue
    INFO = "info"        # informational, no action required


class ValidationIssueType(str, Enum):
    MISSING_DISTANCE_ENTRY = "missing_distance_entry"
    TELEPORTATION = "teleportation"
    NON_POSITIVE_TRAVEL_WINDOW = "non_positive_travel_window"
    SEQUENCE_GAP_OR_DUPLICATE = "sequence_gap_or_duplicate"
    DUPLICATE_STOP = "duplicate_stop"
    DISTANCE_TOTAL_MISMATCH = "distance_total_mismatch"
    OUTLIER_HOP_DISTANCE = "outlier_hop_distance"
    ROUTE_DISCONTINUITY = "route_discontinuity"
    MISSING_COURIER_TYPE = "missing_courier_type"
    MISSING_COURIER = "missing_courier"
    INVALID_ROUTE_TIME_WINDOW = "invalid_route_time_window"


@dataclass
class ValidationIssue:
    severity: ValidationSeverity
    issue_type: ValidationIssueType
    route_id: str
    message: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "issue_type": self.issue_type.value,
            "route_id": self.route_id,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class ValidationConfig:
    # Tolerance multiplier applied to a courier's max speed before an implied
    # speed is flagged as teleportation. e.g. 1.15 => 15% slack overrated speed.
    speed_tolerance: float = 1.15
    # Minimum acceptable travel window in seconds; below this (with nonzero
    # distance) is treated as a hard violation regardless of speed math.
    min_travel_window_seconds: float = 1.0
    # Relative tolerance when comparing sum(hop distances) to the route's
    # declared total_distance_km (0.15 = 15%).
    distance_total_tolerance_pct: float = 0.15
    # Hops further than mean + N * stdev (within a route) are flagged as
    # statistical outliers. Requires >= min_hops_for_outlier_check hops.
    outlier_std_multiplier: float = 3.0
    min_hops_for_outlier_check: int = 4
    # If True, a missing distance-matrix entry (i.e. silent haversine
    # fallback) is an ERROR. If False, it's a WARNING.
    require_distance_matrix_entry: bool = True
    # Max allowed gap (km) between the end of one route and the start of the
    # next route for the same courier, before flagging discontinuity.
    max_inter_route_gap_km: float = 0.5


@dataclass
class ValidationReport:
    issues: List[ValidationIssue] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return not any(i.severity == ValidationSeverity.ERROR for i in self.issues)

    def issues_for(self, route_id: str) -> List[ValidationIssue]:
        return [i for i in self.issues if i.route_id == route_id]

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "summary": self.summary,
            "issues": [i.to_dict() for i in self.issues],
        }

