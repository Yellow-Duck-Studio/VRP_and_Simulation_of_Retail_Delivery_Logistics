from datetime import datetime
from ..fsm import OrderFSM, CourierFSM
from ..schemas.courier import CourierStatus
from .time_manager import TimeManager
from .event_manager import EventType, Event, EventManager
from .state_manager import StateManager
from .route_validator import TripConnectionValidator, ValidationConfig, ValidationReport
from ..utils import PaymentCalculator
from typing import Optional, Dict

class SimulationController:
    def __init__(self, start_time: datetime, time_step_minutes: int = 1,
                 validation_config: Optional[ValidationConfig] = None,
                 strict_validation: bool = True):
        self.time_manager = TimeManager(start_time, time_step_minutes)
        self.event_manager = EventManager()
        self.state_manager = StateManager()
        self.is_running = False
        self.max_steps: Optional[int] = None

        # FSM registries
        self.order_fsms: Dict[str, OrderFSM] = {}
        self.courier_fsms: Dict[str, CourierFSM] = {}

        self.payment_calculator = None

        # Trip connection validation
        self.validator = TripConnectionValidator(self.state_manager, validation_config)
        self.strict_validation = strict_validation
        self.validation_report: Optional[ValidationReport] = None
        self.location_resolver = None

    def validate_routes(self) -> ValidationReport:
        """Runs static trip-connection validation over all loaded routes.

        Safe to call independently of run()/initialize() - e.g. right after
        data_loader.load_simulation_data(), before deciding whether to run
        the simulation at all.
        """
        self.validation_report = self.validator.validate_all()

        event_type = (EventType.ROUTE_VALIDATION_PASSED if self.validation_report.is_valid
                      else EventType.ROUTE_VALIDATION_FAILED)
        self.event_manager.publish(Event(
            event_type,
            self.time_manager.current_time,
            self.validation_report.summary,
            "validator"
        ))

        # Below logger part is for informing user about validation found issues TODO: delegate to logger
        if not self.validation_report.is_valid:
            error_issues = [i for i in self.validation_report.issues
                             if i.severity.value == "error"]
            print(f"[{self.time_manager.current_time}] Route validation found "
                  f"{len(error_issues)} ERROR-level issue(s) across "
                  f"{self.validation_report.summary.get('routes_with_errors', 0)} route(s)")
            for issue in error_issues[:20]:
                print(f"  - [{issue.route_id}] {issue.issue_type.value}: {issue.message}")
            if len(error_issues) > 20:
                print(f"  ... and {len(error_issues) - 20} more")

        warnings = [i for i in self.validation_report.issues
                    if i.severity.value == "warning"]
        if warnings:
            print(f"[{self.time_manager.current_time}] Route validation found "
                  f"{len(warnings)} WARNING-level issue(s)")
            for issue in warnings[:20]:
                print(f"  - [{issue.route_id}] {issue.issue_type.value}: {issue.message}")
            if len(warnings) > 20:
                print(f"  ... and {len(warnings) - 20} more")

        return self.validation_report

    def initialize(self) -> None:
        print(f"[{self.time_manager.current_time}] Simulation initialization")

        report = self.validate_routes()
        if self.strict_validation and not report.is_valid:
            raise ValueError(
                f"Route validation failed with "
                f"{report.summary.get('routes_with_errors', 0)} route(s) containing errors "
                f"(e.g. teleportation, missing distance data, broken sequences). "
                f"Fix the input routes or construct SimulationController with "
                f"strict_validation=False to run anyway."
            )

        # Reuse the validator's resolver so live simulation math and
        # pre-flight validation agree on how locations map to distance-matrix keys.
        self.location_resolver = self.validator.resolver

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
            fsm = CourierFSM(courier, self.state_manager, self.event_manager, self.order_fsms,
                              self.payment_calculator, self.location_resolver)
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

    def get_validation_report(self) -> ValidationReport:
        return self.validation_report

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
            "total_delivery_cost": total_cost,
            "route_validation": self.validation_report.to_dict() if self.validation_report else None,
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