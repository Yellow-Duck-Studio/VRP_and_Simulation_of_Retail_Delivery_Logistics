from datetime import datetime
from ..schemas import Order, OrderStatus
from ..engine.event_manager import EventType, Event, EventManager

class OrderFSM:
    def __init__(self, order: Order, event_manager: EventManager):
        self.order = order
        self.event_manager = event_manager
        self._pending_ready_handled = False  # to fire ORDER_CREATED once

    def handle_ready(self, current_time: datetime) -> None:
        """Transition from PENDING to ASSIGNED when ready_time is reached (actually stays PENDING until assigned)."""
        if (self.order.status == OrderStatus.PENDING and
            self.order.ready_time <= current_time and
            not self._pending_ready_handled):
            self._pending_ready_handled = True
            self.event_manager.publish(Event(
                EventType.ORDER_CREATED,
                current_time,
                {"order_id": self.order.order_id},
                self.order.order_id
            ))

    def assign_to_courier(self, courier_id: str, current_time: datetime) -> None:
        if self.order.status == OrderStatus.PENDING:
            self.order.status = OrderStatus.ASSIGNED
            self.order.assigned_courier_id = courier_id
            self.event_manager.publish(Event(
                EventType.ORDER_ASSIGNED,
                current_time,
                {"order_id": self.order.order_id, "courier_id": courier_id},
                self.order.order_id
            ))

    def pickup(self, current_time: datetime) -> None:
        if self.order.status == OrderStatus.ASSIGNED:
            self.order.status = OrderStatus.IN_TRANSIT
            # Could publish an event if needed

    def deliver(self, current_time: datetime, in_window: bool) -> None:
        if self.order.status in (OrderStatus.ASSIGNED, OrderStatus.IN_TRANSIT):
            self.order.status = OrderStatus.DELIVERED
            # self.order.delivery_time = current_time  currently not in use
            self.event_manager.publish(Event(
                EventType.ORDER_DELIVERED,
                current_time,
                {"order_id": self.order.order_id, "in_window": in_window},
                self.order.order_id
            ))

    def cancel(self, current_time: datetime) -> None:
        if self.order.status not in (OrderStatus.DELIVERED, OrderStatus.CANCELLED):
            self.order.status = OrderStatus.CANCELLED
            self.event_manager.publish(Event(
                EventType.ORDER_CANCELLED,
                current_time,
                {"order_id": self.order.order_id},
                self.order.order_id
            ))