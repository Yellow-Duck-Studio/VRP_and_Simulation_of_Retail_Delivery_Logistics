from pydantic import BaseModel, Field

class CourierType(BaseModel):
    type_id: str
    name: str
    capacity_kg: float = Field(..., gt=0)
    speed_kmh: float = Field(..., gt=0)