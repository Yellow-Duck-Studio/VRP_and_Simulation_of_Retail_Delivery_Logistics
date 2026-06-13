from pydantic import BaseModel, Field
from typing import List
from datetime import datetime, time
from .order import Location


class OperatingHours(BaseModel):
    open_time: time
    close_time: time
    
    def is_open(self, check_time: datetime) -> bool:
        current_time = check_time.time()
        return self.open_time <= current_time <= self.close_time


class InventoryItem(BaseModel):
    product_id: str
    quantity: float
    unit: str = "units"


class Warehouse(BaseModel):
    warehouse_id: str
    name: str
    location: Location
    capacity: float = Field(..., gt=0, description="Total storage capacity")
    operating_hours: OperatingHours
    inventory: List[InventoryItem] = Field(default_factory=list)
    assigned_vehicle_ids: List[str] = Field(default_factory=list)
    is_active: bool = True
    
    def available_capacity(self) -> float:
        used = sum(item.quantity for item in self.inventory)
        return self.capacity - used
    
    def has_vehicle(self, vehicle_id: str) -> bool:
        return vehicle_id in self.assigned_vehicle_ids
