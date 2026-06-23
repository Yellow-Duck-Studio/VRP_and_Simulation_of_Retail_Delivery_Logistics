from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
from .order import Location
from .courier_type import CourierType


class CourierStatus(str, Enum):
    IDLE = "idle"
    LOADING = "loading"
    DELIVERING = "delivering"
    RETURNING = "returning"
    MAINTENANCE = "maintenance"


class AffiliationType(str, Enum):
    SHIFT = "shift"
    EXCHANGE = "exchange"
    TPL = "tpl"


class Courier(BaseModel):
    courier_id: str
    courier_type_id: str = Field(..., description="Courier type id")
    affiliation_type: AffiliationType = Field(..., description="Transport affiliation type")
    current_location: Location
    current_load: float = Field(default=0.0, ge=0, description="Current load in units")
    status: CourierStatus = CourierStatus.IDLE
    assigned_order_ids: List[str] = Field(default_factory=list)
    current_route_id: Optional[str] = None
    planned_route_ids: List[str] = Field(default_factory=list, description="Sorted list of route ids")
    last_updated: datetime = Field(default_factory=datetime.now)
    total_work_hours: float = 0.0
    
    def available_capacity(self, courier_type: 'CourierType') -> float:
        return courier_type.capacity_kg - self.current_load

    def is_available(self) -> bool:
        return self.status == CourierStatus.IDLE
