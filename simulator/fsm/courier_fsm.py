from datetime import datetime, timedelta
from typing import Dict
from ..engine.event_manager import EventType, Event, EventManager
from ..engine.state_manager import StateManager
from ..schemas import Courier, CourierStatus, StopType, Location
from .order_fsm import OrderFSM
from ..utils import PaymentCalculator, get_logger

class CourierFSM:
    def __init__(self, courier: Courier, state_manager: StateManager,
                 event_manager: EventManager, order_fsms: Dict[str, OrderFSM], payment_calculator: PaymentCalculator):
        self.courier = courier
        self.state_manager = state_manager
        self.event_manager = event_manager
        self.order_fsms = order_fsms
        self.progress = None
        self.payment_calculator = payment_calculator
        self.route_start_time = None
        self.logger = get_logger(f"CourierFSM-{courier.courier_id}")

    def start_next_route(self, current_time: datetime) -> bool:
        """Initiates the next planned route. Returns True if started"""
        if not self.courier.planned_route_ids:
            self.logger.debug(f"No planned routes for courier {self.courier.courier_id}")
            return False

        next_route_id = self.courier.planned_route_ids[0]
        route = self.state_manager.routes.get(next_route_id)
        if not route or not route.stops:
            self.logger.warning(f"Route {next_route_id} not found or has no stops")
            return False

        if route.start_time and current_time < route.start_time:
            self.logger.debug(f"Route {next_route_id} not ready (start_time={route.start_time})")
            return False

        self.route_start_time = current_time
        self.courier.status = CourierStatus.DELIVERING
        self.courier.current_route_id = next_route_id
        self.logger.info(f"Starting route {next_route_id} with {len(route.stops)} stops")

        start_loc = self.courier.current_location or route.stops[0].location
        first_stop = route.stops[0]
        travel_seconds = self._travel_time(start_loc, first_stop.location)
        arrival_time = current_time + timedelta(seconds=travel_seconds)
        self.logger.debug(f"Travel to first stop {first_stop.order_id}: {travel_seconds:.1f}s, arrival {arrival_time}")

        self.progress = {
            "current_route_id": next_route_id,
            "next_stop_index": 0,
            "arrival_time": current_time + timedelta(seconds=travel_seconds),
            "from_location": start_loc,
            "segment_distance": self._distance_km(start_loc, first_stop.location)
        }

        self.event_manager.publish(Event(
            EventType.COURIER_DEPARTED,
            current_time,
            {"route_id": next_route_id, "next_stop": first_stop.order_id},
            self.courier.courier_id
        ))

        self.courier.planned_route_ids.pop(0)
        return True

    def handle_arrival(self, current_time: datetime) -> None:
        """Processes arrival at current stop. May wait, pickup, or deliver"""
        if not self.progress:
            return

        route = self.state_manager.routes.get(self.progress["current_route_id"])
        if not route:
            self.logger.warning(f"Route {self.progress['current_route_id']} not found, finishing")
            self.finish_route(current_time)
            return

        stop_idx = self.progress["next_stop_index"]
        if stop_idx >= len(route.stops):
            self.logger.debug(f"All stops completed, finishing route")
            self.finish_route(current_time)
            return

        stop = route.stops[stop_idx]
        order = self.state_manager.orders.get(stop.order_id)
        if not order:
            self.logger.warning(f"Order {stop.order_id} not found, skipping to next stop")
            self.move_to_next_stop(current_time)
            return

        order_fsm = self.order_fsms.get(order.order_id)
        if not order_fsm:
            self.logger.warning(f"OrderFSM for {order.order_id} not found, skipping")
            self.move_to_next_stop(current_time)
            return

        self.logger.debug(f"Arrived at stop {stop_idx+1}/{len(route.stops)}: {stop.stop_type.value} for order {order.order_id}")

        if stop.stop_type == StopType.PICKUP:
            if current_time < order.ready_time:
                wait_seconds = (order.ready_time - current_time).total_seconds()
                self.logger.debug(f"Order {order.order_id} not ready, waiting {wait_seconds:.1f}s")
                self.progress["arrival_time"] = current_time + timedelta(seconds=wait_seconds)
                return
            else:
                # Pickup
                self.logger.info(f"Pickup order {order.order_id}")
                order_fsm.assign_to_courier(self.courier.courier_id, current_time)
                order_fsm.pickup(current_time)
                self.courier.current_load += order.mass_kg
                self.logger.debug(f"Courier load now {self.courier.current_load:.1f} kg")
                self.courier.current_location = stop.location
                self.move_to_next_stop(current_time, service_time=stop.service_duration_minutes)

        elif stop.stop_type == StopType.DELIVERY:
            if current_time < order.delivery_time_window.start:
                wait_seconds = (order.delivery_time_window.start - current_time).total_seconds()
                self.logger.debug(f"Order {order.order_id} delivery window not open, waiting {wait_seconds:.1f}s")
                self.progress["arrival_time"] = current_time + timedelta(seconds=wait_seconds)
                return

            # Deliver
            self.logger.info(f"Delivering order {order.order_id} at {current_time}")
            in_window = order.delivery_time_window.start <= current_time <= order.delivery_time_window.end
            order_fsm.deliver(current_time, in_window)

            self.state_manager.delivery_results[order.order_id] = {
                "delivery_time": current_time.isoformat(),
                "sla_met": in_window
            }

            distance_km = self.progress.get("segment_distance", 0.0)
            self._add_payment(distance_km, order, in_window, current_time)

            self.courier.current_load -= order.mass_kg
            self.logger.debug(f"Courier load now {self.courier.current_load:.1f} kg")
            self.courier.current_location = stop.location
            self.move_to_next_stop(current_time, service_time=stop.service_duration_minutes)

    def move_to_next_stop(self, current_time: datetime, service_time: int = 0) -> None:
        """Plan next stop after service."""
        route = self.state_manager.routes.get(self.progress["current_route_id"])
        if not route:
            self.finish_route(current_time)
            return

        next_stop_idx = self.progress["next_stop_index"] + 1
        if next_stop_idx >= len(route.stops):
            self.finish_route(current_time)
            return

        next_stop = route.stops[next_stop_idx]
        departure_time = current_time + timedelta(minutes=service_time)
        travel_seconds = self._travel_time(self.courier.current_location, next_stop.location)
        arrival_time = departure_time + timedelta(seconds=travel_seconds)
        self.logger.debug(f"Moving to next stop {next_stop.order_id}, arrival at {arrival_time}")

        self.progress["next_stop_index"] = next_stop_idx
        self.progress["arrival_time"] = arrival_time
        self.progress["from_location"] = self.courier.current_location
        self.progress["segment_distance"] = self._distance_km(self.courier.current_location, next_stop.location)

        self.event_manager.publish(Event(
            EventType.COURIER_DEPARTED,
            departure_time,
            {"route_id": route.route_id, "next_stop": next_stop.order_id},
            self.courier.courier_id
        ))

    def finish_route(self, current_time: datetime) -> None:
        self.logger.info(f"Finishing route {self.courier.current_route_id}")
        self.progress = None
        self.courier.current_route_id = None
        if self.route_start_time:
            duration_hours = (current_time - self.route_start_time).total_seconds() / 3600.0
            self.courier.total_work_hours += duration_hours
            self.logger.debug(f"Added {duration_hours:.2f} hours, total work hours {self.courier.total_work_hours:.2f}")
            self.route_start_time = None

        if not self.start_next_route(current_time):
            self.courier.status = CourierStatus.IDLE
            self.logger.info(f"Courier {self.courier.courier_id} is now idle")
            self.event_manager.publish(Event(
                EventType.COURIER_RETURNED,
                current_time,
                {},
                self.courier.courier_id
            ))

    # ------------------------------------------------------------------
    # Helper methods – they use the state_manager for distance and types
    # ------------------------------------------------------------------
    def _distance_km(self, from_loc: Location, to_loc: Location) -> float:
        """Return distance in km using the distance matrix, fallback to haversine."""
        matrix = self.state_manager.distance_matrix
        if matrix is not None:
            from_key = f"{from_loc.latitude},{from_loc.longitude}"
            to_key = f"{to_loc.latitude},{to_loc.longitude}"
            try:
                return matrix.get_distance(from_key, to_key)
            except KeyError:
                pass
        # Fallback: haversine
        from math import radians, sin, cos, sqrt, atan2
        R = 6371.0
        lat1, lon1 = radians(from_loc.latitude), radians(from_loc.longitude)
        lat2, lon2 = radians(to_loc.latitude), radians(to_loc.longitude)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        return R * c

    def _travel_time(self, from_loc: Location, to_loc: Location) -> float:
        """Return travel time in seconds."""
        distance_km = self._distance_km(from_loc, to_loc)
        courier_type = self.state_manager.courier_types.get(self.courier.courier_type_id)
        if courier_type is None:
            raise ValueError(f"Courier type {self.courier.courier_type_id} not found")
        hours = distance_km / courier_type.speed_kmh
        return hours * 3600.0

    def _add_payment(self, distance_km: float, order, in_window: bool, current_time: datetime) -> None:
        """Calculate and add payment for a delivery segment."""
        if self.courier.affiliation_type == "shift":
            self.logger.debug("Shift worker: payment tracked hourly, no per-delivery payment")
            return
        payment = self.payment_calculator.calculate(
            courier=self.courier,
            distance_km=distance_km,
            in_window=in_window,
            duration_hours=0.0
        )
        self.logger.debug(f"Added payment {payment:.2f} rub for delivery {order.order_id}")
        self.state_manager.courier_payments[self.courier.courier_id] = (
                self.state_manager.courier_payments.get(self.courier.courier_id, 0.0) + payment
        )
        self.event_manager.publish(Event(
            EventType.PAYMENT_SENT,
            current_time,
            {"courier_id": self.courier.courier_id, "amount": payment},
            self.courier.courier_id
        ))