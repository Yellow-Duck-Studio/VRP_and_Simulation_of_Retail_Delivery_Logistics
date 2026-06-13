from pydantic import BaseModel, Field
from datetime import datetime
from .order import Location


class Customer(BaseModel):
    customer_id: str
    location: Location
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    
    def estimated_next_order_date(self, last_order_date: datetime) -> datetime:
        """Estimate next order date based on frequency"""
        from datetime import timedelta
        return last_order_date + timedelta(days=self.order_frequency_days)
