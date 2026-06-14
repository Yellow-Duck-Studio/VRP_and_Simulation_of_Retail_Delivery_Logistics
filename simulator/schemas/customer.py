from pydantic import BaseModel, Field
from datetime import datetime
from .order import Location


class Customer(BaseModel):
    customer_id: str
    location: Location
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
