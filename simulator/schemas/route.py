from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from .order import Location


class RouteStop(BaseModel):
    order_id: str
    location: Location
    sequence_number: int = Field(..., ge=1)
    arrival_time: datetime
    departure_time: datetime
    service_duration_minutes: int
    distance_from_previous_km: float = Field(default=0.0, ge=0)
    cumulative_distance_km: float = Field(default=0.0, ge=0)
    
    @property
    def wait_time_minutes(self) -> int:
        if self.arrival_time < self.departure_time:
            return int((self.departure_time - self.arrival_time).total_seconds() / 60) - self.service_duration_minutes
        return 0


class Route(BaseModel):
    route_id: str
    transport_id: str
    warehouse_id: str
    stops: List[RouteStop] = Field(default_factory=list)
    start_time: datetime
    estimated_end_time: datetime
    total_distance_km: float = Field(default=0.0, ge=0)
    total_duration_minutes: int = Field(default=0, ge=0)
    total_demand: float = Field(default=0.0, ge=0)
    status: str = "planned"  # planned, in_progress, completed, cancelled
    
    def add_stop(self, stop: RouteStop) -> None:
        self.stops.append(stop)
        self.total_demand += 0  # Will be calculated from order demand
        self._recalculate_metrics()
    
    def _recalculate_metrics(self) -> None:
        if not self.stops:
            return
        
        self.total_distance_km = max(s.cumulative_distance_km for s in self.stops)
        if self.stops:
            self.total_duration_minutes = int(
                (self.stops[-1].departure_time - self.start_time).total_seconds() / 60
            )
    
    def get_stop_by_order(self, order_id: str) -> Optional[RouteStop]:
        for stop in self.stops:
            if stop.order_id == order_id:
                return stop
        return None
