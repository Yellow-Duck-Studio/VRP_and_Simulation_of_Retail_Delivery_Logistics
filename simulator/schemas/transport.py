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


class AffiliationType(str, Enum):
    SHIFT = "shift"
    EXCHANGE = "exchange"
    TPL = "tpl"


class Transport(BaseModel):
    transport_id: str
    courier_type_id: str = Field(..., description="Courier type id")
    affiliation_type: AffiliationType = Field(..., description="Transport affiliation type")
    current_location: Location
    current_load: float = Field(default=0.0, ge=0, description="Current load in units")
    status: TransportStatus = TransportStatus.IDLE
    assigned_order_ids: List[str] = Field(default_factory=list)
    current_route_id: Optional[str] = None
    planned_route_ids: List[str] = Field(default_factory=list, description="Sorted list of route ids")
    fuel_level: float | None = Field(default=100.0, ge=0, le=100, description="Fuel percentage")
    last_updated: datetime = Field(default_factory=datetime.now)
    
    def available_capacity(self, courier_type: 'CourierType') -> float:
        return courier_type.capacity_kg - self.current_load
    
    def can_accept_order(self, courier_type: 'CourierType', demand: float) -> bool:
        return self.available_capacity(courier_type) >= demand and self.status in [TransportStatus.IDLE, TransportStatus.LOADING]
    
    def is_available(self) -> bool:
        return self.status == TransportStatus.IDLE and self.fuel_level > 10
