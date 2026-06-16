from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Set, Tuple, Optional

@dataclass(frozen=True)
class Order:
    order_id: int
    warehouse_id: int
    lat: float
    lon: float
    pickup_ready_at: datetime
    delivery_deadline_at: datetime
    total_mass_kg: float

@dataclass(frozen=True)
class Constraint:
    max_order_count: int
    max_weight_per_transport: Dict[str, float] # e.g. {'bike': 10.0, 'foot': 10.0, 'car': 30.0}
    speeds_kmh: Dict[str, float]               # e.g. {'bike': 15.0, 'foot': 5.0, 'car': 40.0}
    transport_distribution: Dict[str, float]   # e.g. {'car': 0.8, 'bike': 0.15, 'foot': 0.05}

@dataclass
class Trip:
    trip_id: int
    warehouse_id: int
    transport_type: str
    order_ids: List[int] = field(default_factory=list)

@dataclass
class Individual:
    """Represents a single candidate solution (a full clusterization)"""
    trips: Dict[int, Trip] = field(default_factory=dict)
    fitness_score: float = float('inf')
    is_valid: bool = False

    def get_trip_sets(self) -> frozenset:
        """Used to uniquely hash the state of this clusterization for the Archive."""
        return frozenset(
            frozenset(trip.order_ids) for trip in self.trips.values() if trip.order_ids
        )