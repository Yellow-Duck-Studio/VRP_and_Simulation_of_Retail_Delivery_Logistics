from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class Location(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    address: Optional[str] = None


class TimeWindow(BaseModel):
    start: datetime
    end: datetime
    
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() / 60)


class Order(BaseModel):
    order_id: str
    customer_id: str
    warehouse_id: str = Field(..., description="Warehouse this order is bound to")
    location: Location
    demand: float = Field(..., gt=0, description="Demand in units (weight, volume, etc.)")
    time_window: TimeWindow
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    assigned_transport_id: Optional[str] = None
    cluster_id: Optional[str] = None

    mass_kg: float = Field(..., gt=0, description="Order mass in kg")
    ready_time: datetime = Field(..., description="Time when item is ready for pickup")
    
    @property
    def pickup_ready_time(self) -> datetime:
        """Time when order is ready for pickup (from clustering task)"""
        return self.ready_time
    
    @property
    def deadline(self) -> datetime:
        """Delivery deadline (from clustering task)"""
        return self.time_window.end
    
    @property
    def weight(self) -> float:
        """Order weight (from clustering task)"""
        return self.mass_kg
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
