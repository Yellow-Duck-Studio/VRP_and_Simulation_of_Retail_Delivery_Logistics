from datetime import datetime
from ..fsm import OrderFSM, CourierFSM
from .time_manager import TimeManager
from .event_manager import EventType, Event, EventManager
from .state_manager import StateManager
from typing import Optional, Dict

class SimulationController:
    def __init__(self, start_time: datetime, time_step_minutes: int = 1):
        self.time_manager = TimeManager(start_time, time_step_minutes)
        self.event_manager = EventManager()
        self.state_manager = StateManager()
        self.is_running = False
        self.max_steps: Optional[int] = None

        # FSM registries
        self.order_fsms: Dict[str, OrderFSM] = {}
        self.courier_fsms: Dict[str, CourierFSM] = {}

    def initialize(self) -> None:
        print(f"[{self.time_manager.current_time}] Simulation initialization")
        self.event_manager.publish(Event(
            EventType.SIMULATION_STARTED,
            self.time_manager.current_time,
            {},
            "simulator"
        ))

        for order in self.state_manager.orders.values():
            self.order_fsms[order.order_id] = OrderFSM(order, self.event_manager)

        for courier in self.state_manager.couriers.values():
            fsm = CourierFSM(courier, self.state_manager, self.event_manager, self.order_fsms)
            self.courier_fsms[courier.courier_id] = fsm
            if courier.planned_route_ids:
                fsm.start_next_route(self.time_manager.current_time)

    def step(self) -> bool:
        """Execute one simulation step."""
        if self.max_steps and self.time_manager.total_steps >= self.max_steps:
            return False

        current_time = self.time_manager.advance()
        self.state_manager.save_state(current_time)
        self._process_step_logic(current_time)
        return True

    def _process_step_logic(self, current_time: datetime) -> None:
        # 1. Let each order check if it becomes ready (fires ORDER_CREATED)
        for fsm in self.order_fsms.values():
            fsm.handle_ready(current_time)

        # 2. Let each courier handle arrivals if they have reached their stop
        for fsm in self.courier_fsms.values():
            if fsm.progress and fsm.progress["arrival_time"] <= current_time:
                fsm.handle_arrival(current_time)

    def run(self, max_steps: Optional[int] = None) -> None:
        self.max_steps = max_steps
        self.is_running = True
        self.initialize()

        while self.is_running:
            if not self.step():
                break

        self.event_manager.publish(Event(
            EventType.SIMULATION_ENDED,
            self.time_manager.current_time,
            {},
            "simulator"
        ))

    def stop(self) -> None:
        self.is_running = False

    def get_metrics(self) -> dict:
        return self.state_manager.get_metrics()

    def get_results(self) -> dict:
        """Aggregate final delivery times, SLA, payments."""
        delivery_times = {}
        in_window = {}
        for order_id, res in self.state_manager.delivery_results.items():
            delivery_times[order_id] = res.get("delivery_time")
            in_window[order_id] = res.get("sla_met", False)

        courier_payments = self.state_manager.courier_payments
        total_cost = sum(courier_payments.values())

        return {
            "order_delivery_times": delivery_times,
            "order_delivered_in_window": in_window,
            "courier_payments": courier_payments,
            "total_delivery_cost": total_cost
        }