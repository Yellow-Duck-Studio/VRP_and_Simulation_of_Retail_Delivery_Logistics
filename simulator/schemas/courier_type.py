from pydantic import BaseModel, Field

class CourierType(BaseModel):
    type_id: str
    name: str
    capacity_kg: float = Field(..., gt=0, description="Courier capacity in kg")
    speed_kmh: float = Field(default=50.0, gt=0, description="Average speed in km/h")