from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import List, Callable, Optional, Dict

class EventType(str, Enum):
    ORDER_CREATED = "Order Created"
    ORDER_ASSIGNED = "Order Assigned"
    ORDER_DELIVERED = "Order Delivered"
    ORDER_CANCELLED = "Order Cancelled"
    COURIER_DEPARTED = "Courier Departed"
    COURIER_ARRIVED = "Courier Arrived"
    COURIER_RETURNED = "Courier Returned"
    SIMULATION_STARTED = "Simulation Started"
    SIMULATION_ENDED = "Simulation Ended"
    PAYMENT_SENT = "Payment Sent"
    ROUTE_VALIDATION_PASSED = "Route Validation Passed"
    ROUTE_VALIDATION_FAILED = "Route Validation Failed"

@dataclass
class Event:
    event_type: EventType
    timestamp: datetime
    data: dict
    entity_id: str

class EventManager:
    def __init__(self):
        self.events: List[Event] = []
        self.event_handlers: Dict[EventType, List[Callable]] = {}

    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        self.event_handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: Event) -> None:
        self.events.append(event)
        for handler in self.event_handlers.get(event.event_type, []):
            handler(event)

    def get_events(self, event_type: Optional[EventType] = None) -> List[Event]:
        if event_type:
            return [e for e in self.events if e.event_type == event_type]
        return self.events.copy()

    def clear(self) -> None:
        self.events.clear()