from pydantic import BaseModel, Field
from typing import List
from datetime import datetime, time
from .order import Location


class Warehouse(BaseModel):
    warehouse_id: str
    location: Location

