from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum
from .order import Location


class StopType(str, Enum):
    PICKUP = "pickup"
    DELIVERY = "delivery"


class RouteStop(BaseModel):
    order_id: str
    location: Location
    stop_type: StopType
    sequence_number: int = Field(..., ge=1)
    service_duration_minutes: float = Field(default=5, ge=0)
    planned_arrival_time: Optional[datetime] = None
    planned_departure_time: Optional[datetime] = None


class Route(BaseModel):
    route_id: str
    courier_id: str
    warehouse_id: str
    start_location: Location
    end_location: Location
    start_time: datetime
    status: str = "planned"  # planned, in_progress, completed, cancelled
    stops: List[RouteStop] = Field(default_factory=list)