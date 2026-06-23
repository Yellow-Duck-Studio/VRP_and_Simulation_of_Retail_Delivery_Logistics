from datetime import datetime, timedelta
from typing import Optional
from ..schemas import CourierStatus, StopType


class TimeManager:
    def __init__(self, start_time: datetime, time_step_minutes: int = 1):
        self.current_time = start_time
        self.time_step = timedelta(minutes=time_step_minutes)
        self.start_time = start_time
        self.total_steps = 0

    def advance(self) -> datetime:
        self.current_time += self.time_step
        self.total_steps += 1
        return self.current_time

    def reset(self, start_time: Optional[datetime] = None) -> None:
        self.current_time = start_time or self.start_time
        self.total_steps = 0