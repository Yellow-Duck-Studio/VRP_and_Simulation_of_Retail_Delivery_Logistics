from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from .schemas import (
    Order, Warehouse, Courier, CourierType, CourierStatus, Route, StopType,
    OrderStatus, DistanceMatrix, Location
)


class EventType(str, Enum):
    ORDER_CREATED = "order_created"
    ORDER_ASSIGNED = "order_assigned"
    COURIER_DEPARTED = "courier_departed"
    COURIER_ARRIVED = "courier_arrived"
    ORDER_DELIVERED = "order_delivered"
    COURIER_RETURNED = "courier_returned"
    SIMULATION_STARTED = "simulation_started"
    SIMULATION_ENDED = "simulation_ended"
    PAYMENT_SENT = "payment_sent"


@dataclass
class Event:
    event_type: EventType
    timestamp: datetime
    data: dict
    entity_id: str


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


class EventManager:
    def __init__(self):
        self.events: List[Event] = []
        self.event_handlers: Dict[EventType, List[Callable]] = {}

    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)

    def publish(self, event: Event) -> None:
        self.events.append(event)
        if event.event_type in self.event_handlers:
            for handler in self.event_handlers[event.event_type]:
                handler(event)

    def get_events(self, event_type: Optional[EventType] = None) -> List[Event]:
        if event_type:
            return [e for e in self.events if e.event_type == event_type]
        return self.events.copy()

    def clear(self) -> None:
        self.events.clear()


class StateManager:
    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self.warehouses: Dict[str, Warehouse] = {}
        self.couriers: Dict[str, Courier] = {}
        self.courier_types: Dict[str, CourierType] = {}
        self.routes: Dict[str, Route] = {}
        self.distance_matrix: Optional[DistanceMatrix] = None
        self.history: List[dict] = []
        self.delivery_results: Dict[str, dict] = {}
        self.courier_payments: Dict[str, float] = {}

    def add_order(self, order: Order) -> None:
        self.orders[order.order_id] = order
    
    def add_warehouse(self, warehouse: Warehouse) -> None:
        self.warehouses[warehouse.warehouse_id] = warehouse

    def add_courier(self, courier: Courier) -> None:
        self.couriers[courier.courier_id] = courier

    def add_courier_type(self, courier_type: CourierType) -> None:
        self.courier_types[courier_type.type_id] = courier_type
    
    def add_route(self, route: Route) -> None:
        self.routes[route.route_id] = route

    def set_distance_matrix(self, matrix: DistanceMatrix) -> None:
        self.distance_matrix = matrix

    def get_order(self, order_id: str) -> Optional[Order]:
        return self.orders.get(order_id)

    def get_pending_orders(self) -> List[Order]:
        return [o for o in self.orders.values() if o.status == OrderStatus.PENDING]

    def get_available_couriers(self) -> List[Courier]:
        return [c for c in self.couriers.values() if c.is_available()]

    def save_state(self, timestamp: datetime) -> None:
        state = {
            "timestamp": timestamp.isoformat(),
            "orders_count": len(self.orders),
            "pending_orders": len(self.get_pending_orders()),
            "couriers_count": len(self.couriers),
            "available_couriers": len(self.get_available_couriers()),
        }
        self.history.append(state)
    
    def get_metrics(self) -> dict:
        if not self.history:
            return {}
        
        delivered_orders = sum(1 for o in self.orders.values() if o.status == OrderStatus.DELIVERED)
        total_orders = len(self.orders)

        sla_hits = sum(1 for res in self.delivery_results.values() if res.get("sla_met", False))

        return {
            "total_orders": total_orders,
            "delivered_orders": delivered_orders,
            "sla_hit_rate": sla_hits / total_orders if total_orders > 0 else 0,
            "pending_orders": len(self.get_pending_orders()),
            "total_couriers": len(self.couriers),
            "available_couriers": len(self.get_available_couriers()),
            "simulation_steps": len(self.history),
        }


class SimulationController:
    def __init__(self, start_time: datetime, time_step_minutes: int = 1):
        self.time_manager = TimeManager(start_time, time_step_minutes)
        self.event_manager = EventManager()
        self.state_manager = StateManager()
        self.is_running = False
        self.max_steps: Optional[int] = None
        self.courier_progress: Dict[str, dict] = {}

    def initialize(self) -> None:
        print(f"[{self.time_manager.current_time}] Simulation initialization")
        self.event_manager.publish(Event(
            event_type=EventType.SIMULATION_STARTED,
            timestamp=self.time_manager.current_time,
            data={},
            entity_id="simulator"
        ))
        for courier in self.state_manager.couriers.values():
            if courier.status == CourierStatus.IDLE and courier.planned_route_ids:
                print(f"  Courier {courier.courier_id} has planned_route_ids: {courier.planned_route_ids}")
                self._start_next_route(courier, self.time_manager.current_time)
            else:
                print(
                    f"  Courier {courier.courier_id} not started: status={courier.status}, planned_route_ids={courier.planned_route_ids}")
    
    def step(self) -> bool:
        """Execute one simulation step"""
        if self.max_steps and self.time_manager.total_steps >= self.max_steps:
            return False
        
        current_time = self.time_manager.advance()
        self.state_manager.save_state(current_time)
        
        # Process pending orders, vehicle movements, etc.
        self._process_step_logic(current_time)
        
        return True

    def _process_step_logic(self, current_time: datetime) -> None:
        """Core simulation logic for each step"""
        if not hasattr(self, '_created_orders'):
            self._created_orders = set()
        for order in self.state_manager.orders.values():
            if (order.status == OrderStatus.PENDING and
                    order.ready_time <= current_time and
                    order.order_id not in self._created_orders):
                print(f"[{current_time}] Order {order.order_id} became ready (first time)")
                self._created_orders.add(order.order_id)
                self.event_manager.publish(Event(
                    event_type=EventType.ORDER_CREATED,
                    timestamp=current_time,
                    data={"order_id": order.order_id},
                    entity_id=order.order_id
                ))

        for courier_id, progress in list(self.courier_progress.items()):
            courier = self.state_manager.couriers.get(courier_id)
            if not courier:
                continue

            if progress["arrival_time"] <= current_time:
                self._handle_arrival(courier, progress, current_time)

    def _start_next_route(self, courier: Courier, current_time: datetime) -> None:
        """Starts next route for every courier (from list planned_route_ids)."""
        print(f"[{current_time}] Courier {courier.courier_id} starts next route")
        if not courier.planned_route_ids:
            print(f"  No planned routes for {courier.courier_id}")
            return

        next_route_id = courier.planned_route_ids[0]
        route = self.state_manager.routes.get(next_route_id)
        if not route:
            print(f"  Route {next_route_id} not found!")
            return

        if not route or not route.stops:
            print(f"  Route {next_route_id} has no stops!")
            self._finish_route(courier, current_time)
            return

        courier.status = CourierStatus.DELIVERING
        courier.current_route_id = next_route_id

        start_loc = courier.current_location
        if start_loc is None:
            start_loc = route.stops[0].location

        print(f"  Courier {courier.courier_id} starts route {route.route_id} with {len(route.stops)} stops")
        first_stop = route.stops[0]
        print(f"  First stop: {first_stop.order_id} ({first_stop.stop_type.value})")
        travel_seconds = self._travel_time_seconds(courier, start_loc, first_stop.location)
        arrival_time = current_time + timedelta(seconds=travel_seconds)

        self.courier_progress[courier.courier_id] = {
            "current_route_id": next_route_id,
            "next_stop_index": 0,
            "arrival_time": arrival_time,
            "from_location": start_loc,
            "segment_distance": self._distance_km(start_loc, first_stop.location)
        }

        self.event_manager.publish(Event(
            event_type=EventType.COURIER_DEPARTED,
            timestamp=current_time,
            data={"route_id": next_route_id, "next_stop": first_stop.order_id},
            entity_id=courier.courier_id
        ))

    def _handle_arrival(self, courier: Courier, progress: dict, current_time: datetime) -> None:
        """Handles arrival to current stop"""
        route = self.state_manager.routes.get(progress["current_route_id"])
        if not route:
            self._finish_route(courier, current_time)
            return

        stop_idx = progress["next_stop_index"]
        if stop_idx >= len(route.stops):
            self._finish_route(courier, current_time)
            return

        stop = route.stops[stop_idx]
        order = self.state_manager.orders.get(stop.order_id)
        if not order:
            self._move_to_next_stop(courier, progress, current_time)
            return

        print(
            f"[{current_time}] Courier {courier.courier_id} arrived at stop {stop_idx} (order {stop.order_id}, type {stop.stop_type.value})")

        if stop.stop_type == StopType.PICKUP: # PICKUP
            if current_time < order.ready_time:
                wait_seconds = (order.ready_time - current_time).total_seconds() # Currently just wait
                print(
                    f"  Order {order.order_id} not ready yet (ready_time={order.ready_time}), waiting {wait_seconds} sec")
                new_arrival = current_time + timedelta(seconds=wait_seconds)
                progress["arrival_time"] = new_arrival
                return
            else:
                print(f"  Order {order.order_id} is ready, picking up")

            order.status = OrderStatus.ASSIGNED
            order.assigned_courier_id = courier.courier_id
            courier.current_load += order.mass_kg

            self.event_manager.publish(Event(
                event_type=EventType.ORDER_ASSIGNED,
                timestamp=current_time,
                data={"order_id": order.order_id},
                entity_id=courier.courier_id
            ))

            courier.current_location = stop.location

            self._move_to_next_stop(courier, progress, current_time, service_time=stop.service_duration_minutes)

        else: # DELIVERY
            print(f"  Delivering order {order.order_id}, delivery time {current_time}")
            order.status = OrderStatus.DELIVERED
            delivery_time = current_time
            in_window = order.delivery_time_window.start <= delivery_time <= order.delivery_time_window.end

            self.state_manager.delivery_results[order.order_id] = {
                "delivery_time": delivery_time.isoformat(),
                "sla_met": in_window
            }

            distance_km = progress.get("segment_distance", 0.0)
            self._add_payment(courier, distance_km, order)

            courier.current_load -= order.mass_kg

            self.event_manager.publish(Event(
                event_type=EventType.ORDER_DELIVERED,
                timestamp=current_time,
                data={"order_id": order.order_id, "in_window": in_window},
                entity_id=courier.courier_id
            ))

            courier.current_location = stop.location

            self._move_to_next_stop(courier, progress, current_time, service_time=stop.service_duration_minutes)

    def _move_to_next_stop(self, courier: Courier, progress: dict, current_time: datetime,
                           service_time: int = 0) -> None:
        """Plans arrival on the next stop considering service time"""
        print(
            f"[{current_time}] Courier {courier.courier_id} finished service, moving to next stop (service time {service_time} min)")
        route = self.state_manager.routes.get(progress["current_route_id"])
        if not route:
            self._finish_route(courier, current_time)
            return

        next_stop_idx = progress["next_stop_index"] + 1
        if next_stop_idx >= len(route.stops):
            print(f"  All stops completed, route finished")
            self._finish_route(courier, current_time)
            return

        next_stop = route.stops[next_stop_idx]
        departure_time = current_time + timedelta(minutes=service_time)
        travel_seconds = self._travel_time_seconds(courier, courier.current_location, next_stop.location)
        arrival_time = departure_time + timedelta(seconds=travel_seconds)

        print(f"  Next stop: {next_stop.order_id} ({next_stop.stop_type.value}), arrival at {arrival_time}")

        progress["next_stop_index"] = next_stop_idx
        progress["arrival_time"] = arrival_time
        progress["from_location"] = courier.current_location
        progress["segment_distance"] = self._distance_km(courier.current_location, next_stop.location)

        # optional:
        self.event_manager.publish(Event(
            event_type=EventType.COURIER_DEPARTED,
            timestamp=departure_time,
            data={"route_id": route.route_id, "next_stop": next_stop.order_id},
            entity_id=courier.courier_id
        ))

    def _finish_route(self, courier: Courier, current_time: datetime) -> None:
        """Finishes current route and starts next one if present"""
        print(f"[{current_time}] Courier {courier.courier_id} finished route {courier.current_route_id}")
        self.courier_progress.pop(courier.courier_id, None)

        if courier.current_route_id in courier.planned_route_ids:
            idx = courier.planned_route_ids.index(courier.current_route_id)
            next_idx = idx + 1
            if next_idx < len(courier.planned_route_ids):
                print(f"  Switching to next route {next_idx}")
                courier.current_route_id = None
                self._start_next_route(courier, current_time)
                return

        print(f"  All routes completed, courier is idle")

        courier.status = CourierStatus.IDLE
        courier.current_route_id = None

        self.event_manager.publish(Event(
            event_type=EventType.COURIER_RETURNED,
            timestamp=current_time,
            data={},
            entity_id=courier.courier_id
        ))

    def _travel_time_seconds(self, courier: Courier, from_loc: Location, to_loc: Location) -> float:
        """Returns time in seconds to travel between two locations"""
        distance_km = self._distance_km(from_loc, to_loc)
        courier_type = self.state_manager.courier_types.get(courier.courier_type_id)
        if not courier_type:
            raise ValueError(f"Courier type {courier.courier_type_id} not found")
        hours = distance_km / courier_type.speed_kmh
        return hours * 3600.0

    def _distance_km(self, from_loc: Location, to_loc: Location) -> float:
        """Returns distance in km (from distance matrix)."""
        matrix = self.state_manager.distance_matrix
        if matrix:
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
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c

    def _add_payment(self, courier: Courier, distance_km: float, order: Order) -> None:
        """Sends payment to courier for segment (can be stored in different field)"""
        rate_per_km = 50.0
        window_bonus = 100.0
        in_window = self.state_manager.delivery_results.get(order.order_id, {}).get("sla_met", False)
        bonus = window_bonus if in_window else 0.0

        multiplier = {
            "shift": 1.0,
            "exchange": 1.2,
            "3pl": 0.9
        }.get(courier.affiliation_type, 1.0)

        payment = (rate_per_km * distance_km + bonus) * multiplier

        self.state_manager.courier_payments[courier.courier_id] = self.state_manager.courier_payments.get(
            courier.courier_id, 0.0) + payment

        self.event_manager.publish(Event(
            event_type=EventType.PAYMENT_SENT,
            timestamp=self.time_manager.current_time,
            data={"courier_id": courier.courier_id, "amount": payment},
            entity_id=courier.courier_id
        ))

    def get_results(self) -> dict:
        """Returns results of simulation"""
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
    
    def run(self, max_steps: Optional[int] = None) -> None:
        """Run the simulation"""
        self.max_steps = max_steps
        self.is_running = True
        self.initialize()
        
        while self.is_running:
            if not self.step():
                break
        
        self.event_manager.publish(Event(
            event_type=EventType.SIMULATION_ENDED,
            timestamp=self.time_manager.current_time,
            data={},
            entity_id="simulator"
        ))
    
    def stop(self) -> None:
        """Stop the simulation"""
        self.is_running = False


    def get_metrics(self) -> dict:
        """Get current simulation metrics"""
        return self.state_manager.get_metrics()
