from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class OrderData:
    order_id: int
    warehouse_id: int
    lat: float
    lon: float
    pickup_ready_at: datetime
    delivery_deadline_at: datetime
    total_mass_kg: float


@dataclass(frozen=True)
class ConstraintData:
    max_order_count: int
    max_weight_per_transport: Dict[str, float]
    speeds_kmh: Dict[str, float]
    transport_distribution: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskContext:
    task_id: str
    orders: List[OrderData]
    warehouses: Dict[int, tuple[float, float]]
    constraints: ConstraintData


@dataclass(frozen=True)
class PipelineConfig:
    initializer: str
    improver: Optional[str] = None
    initializer_config: Dict[str, Any] = field(default_factory=dict)
    improver_config: Dict[str, Any] = field(default_factory=dict)
    metrics_config: Dict[str, Any] = field(default_factory=dict)
    max_solutions: int = 100


@dataclass(frozen=True)
class TripResult:
    trip_id: int
    warehouse_id: int
    transport_type: str
    order_ids: List[int]


@dataclass(frozen=True)
class MetricsResult:
    is_valid: bool
    fitness_score: float
    t_total_hours: float
    p_hard: float
    p_capacity: float
    p_mass: float
    p_sla: float
    p_sync: float
    p_fleet: float
    p_direction: float
    trip_count: int
    total_distance_km: float
    total_travel_time_hours: float
    late_orders_count: int
    total_lateness_minutes: float
    max_lateness_minutes: float
    avg_orders_per_trip: float
    total_orders: int


@dataclass
class Solution:
    solution_id: str
    pipeline: List[str]
    source_stage: str
    trips: List[TripResult]
    metrics: Optional[MetricsResult]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineRunResult:
    task_id: str
    pipeline_name: str
    config: PipelineConfig
    solutions: List[Solution]
    summary: Dict[str, Any] = field(default_factory=dict)
