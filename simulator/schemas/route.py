from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from .order import Location


class Route(BaseModel):
    route_id: str
    transport_id: str
    warehouse_id: str
    start_location: Location
    end_location: Location
    start_time: datetime
    end_time: datetime
    total_distance_km: float = Field(default=0.0, ge=0)
    total_duration_minutes: int = Field(default=0, ge=0)
    status: str = "planned"  # planned, in_progress, completed, cancelled
    
    def _recalculate_metrics(self) -> None:
        if not self.stops:
            return
        
        self.total_distance_km = max(s.cumulative_distance_km for s in self.stops)
        if self.stops:
            self.total_duration_minutes = int(
                (self.stops[-1].departure_time - self.start_time).total_seconds() / 60
            )
