from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
from .order import Location


class TransportStatus(str, Enum):
    IDLE = "idle"
    LOADING = "loading"
    DELIVERING = "delivering"
    RETURNING = "returning"
    MAINTENANCE = "maintenance"


class TransportType(str, Enum):
    FOOT = "foot"
    BIKE = "bike"
    CAR = "car"


class Transport(BaseModel):
    transport_id: str
    vehicle_type: TransportType
    capacity: float = Field(..., gt=0, description="Vehicle capacity in units")
    current_location: Location
    current_load: float = Field(default=0.0, ge=0, description="Current load in units")
    status: TransportStatus = TransportStatus.IDLE
    assigned_order_ids: List[str] = Field(default_factory=list)
    current_route_id: Optional[str] = None
    fuel_level: float | None = Field(default=100.0, ge=0, le=100, description="Fuel percentage")
    speed_kmh: float | None = Field(default=50.0, gt=0, description="Average speed in km/h")
    last_updated: datetime = Field(default_factory=datetime.now)
    
    def available_capacity(self) -> float:
        return self.capacity - self.current_load
    
    def can_accept_order(self, demand: float) -> bool:
        return self.available_capacity() >= demand and self.status in [TransportStatus.IDLE, TransportStatus.LOADING]
    
    def is_available(self) -> bool:
        return self.status == TransportStatus.IDLE and self.fuel_level > 10
