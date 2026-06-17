from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from .order import Location


class Route(BaseModel):
    route_id: str
    courier_id: str
    warehouse_id: str
    start_location: Location
    end_location: Location
    start_time: datetime
    end_time: datetime
    total_distance_km: float = Field(default=0.0, ge=0)
    total_duration_minutes: int = Field(default=0, ge=0)
    status: str = "planned"  # planned, in_progress, completed, cancelled