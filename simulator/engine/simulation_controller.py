from datetime import datetime
from ..fsm import OrderFSM, CourierFSM
from ..schemas.courier import CourierStatus
from .time_manager import TimeManager
from .event_manager import EventType, Event, EventManager
from .state_manager import StateManager
from ..utils import PaymentCalculator
from typing import Optional, Dict
from ..utils.logger import get_logger

class SimulationController:
    def __init__(self, start_time: datetime, time_step_minutes: int = 1):
        self.logger = get_logger("SimulationController")
        self.time_manager = TimeManager(start_time, time_step_minutes)
        self.event_manager = EventManager()
        self.state_manager = StateManager()
        self.is_running = False
        self.max_steps: Optional[int] = None

        # FSM registries
        self.order_fsms: Dict[str, OrderFSM] = {}
        self.courier_fsms: Dict[str, CourierFSM] = {}

        self.payment_calculator = None

    def initialize(self) -> None:
        self.logger.info(f"Simulation initialization at {self.time_manager.current_time}")
        self.logger.info(f"Entities: {len(self.state_manager.orders)} orders, "
                         f"{len(self.state_manager.couriers)} couriers, "
                         f"{len(self.state_manager.routes)} routes")

        config = self.state_manager.payment_config or {}
        self.payment_calculator = PaymentCalculator(config)

        self.event_manager.publish(Event(
            EventType.SIMULATION_STARTED,
            self.time_manager.current_time,
            {},
            "simulator"
        ))

        for order in self.state_manager.orders.values():
            self.order_fsms[order.order_id] = OrderFSM(order, self.event_manager)

        for courier in self.state_manager.couriers.values():
            fsm = CourierFSM(courier, self.state_manager, self.event_manager, self.order_fsms, self.payment_calculator)
            self.courier_fsms[courier.courier_id] = fsm
            if courier.planned_route_ids:
                fsm.start_next_route(self.time_manager.current_time)

    def step(self) -> bool:
        """Execute one simulation step."""
        if self.max_steps and self.time_manager.total_steps >= self.max_steps:
            self.logger.info(f"Max steps ({self.max_steps}) reached, stopping")
            return False

        current_time = self.time_manager.advance()
        if self.time_manager.total_steps % 10 == 0:
            self.logger.info(f"Step {self.time_manager.total_steps} at {current_time}")
        self.logger.debug(f"Step {self.time_manager.total_steps} details...")
        self.state_manager.save_state(current_time)
        self._process_step_logic(current_time)
        return True

    def _process_step_logic(self, current_time: datetime) -> None:
        # 1. Let each order check if it becomes ready
        for fsm in self.order_fsms.values():
            fsm.handle_ready(current_time)

        # 2. Try to start idle couriers with pending routes
        for fsm in self.courier_fsms.values():
            if (fsm.courier.status == CourierStatus.IDLE
                    and fsm.courier.planned_route_ids):
                fsm.start_next_route(current_time)

        # 3. Let each courier handle arrivals
        for fsm in self.courier_fsms.values():
            if fsm.progress and fsm.progress["arrival_time"] <= current_time:
                fsm.handle_arrival(current_time)

    def run(self, max_steps: Optional[int] = None) -> None:
        self.logger.info("Starting simulation run")
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
        self.logger.info("Simulation finished")
        metrics = self.get_metrics()
        self.logger.info(f"Delivered: {metrics['delivered_orders']}/{metrics['total_orders']}, "
                         f"SLA hit rate: {metrics['sla_hit_rate']:.2%}")

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

        self._compute_shift_payments()

        courier_payments = self.state_manager.courier_payments
        total_cost = sum(courier_payments.values())

        return {
            "order_delivery_times": delivery_times,
            "order_delivered_in_window": in_window,
            "courier_payments": courier_payments,
            "total_delivery_cost": total_cost
        }

    def _compute_shift_payments(self):
        for courier in self.state_manager.couriers.values():
            if courier.affiliation_type == "shift" and courier.total_work_hours > 0:
                payment = self.payment_calculator.calculate(
                    courier=courier,
                    distance_km=0.0,
                    in_window=False,
                    duration_hours=courier.total_work_hours
                )
                self.state_manager.courier_payments[courier.courier_id] = (
                        self.state_manager.courier_payments.get(courier.courier_id, 0.0) + payment
                )