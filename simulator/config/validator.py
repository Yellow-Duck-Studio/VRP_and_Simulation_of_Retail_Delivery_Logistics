from enum import Enum
from dataclasses import dataclass, field
from typing import List


class ValidationSeverity(str, Enum):
    ERROR = "error"      # physically impossible / contract-breaking -> should block a run
    WARNING = "warning"  # suspicious, likely a solver/data quality issue
    INFO = "info"        # informational, no action required


class ValidationIssueType(str, Enum):
    MISSING_DISTANCE_ENTRY = "missing_distance_entry"
    DUPLICATE_STOP = "duplicate_stop"
    ROUTE_DISCONTINUITY = "route_discontinuity"
    MISSING_COURIER_TYPE = "missing_courier_type"
    MISSING_COURIER = "missing_courier"


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

