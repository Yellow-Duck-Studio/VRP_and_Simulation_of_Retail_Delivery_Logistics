from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from .schemas import (
    Order, Warehouse, Transport, Route,
    OrderStatus, TransportStatus
)


class EventType(str, Enum):
    ORDER_CREATED = "order_created"
    ORDER_ASSIGNED = "order_assigned"
    VEHICLE_DEPARTED = "vehicle_departed"
    VEHICLE_ARRIVED = "vehicle_arrived"
    ORDER_DELIVERED = "order_delivered"
    VEHICLE_RETURNED = "vehicle_returned"
    SIMULATION_STARTED = "simulation_started"
    SIMULATION_ENDED = "simulation_ended"


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
        self.vehicles: Dict[str, Transport] = {}
        self.courier_types: Dict[str, CourierType] = {}
        self.routes: Dict[str, Route] = {}
        self.history: List[dict] = []
    
    def add_order(self, order: Order) -> None:
        self.orders[order.order_id] = order
    
    def add_warehouse(self, warehouse: Warehouse) -> None:
        self.warehouses[warehouse.warehouse_id] = warehouse
    
    def add_vehicle(self, vehicle: Transport) -> None:
        self.vehicles[vehicle.vehicle_id] = vehicle

    def add_courier_type(self, courier_type: CourierType) -> None:
        self.courier_types[courier_type.type_id] = courier_type
    
    def add_route(self, route: Route) -> None:
        self.routes[route.route_id] = route
    
    def get_order(self, order_id: str) -> Optional[Order]:
        return self.orders.get(order_id)
    
    def get_warehouse(self, warehouse_id: str) -> Optional[Warehouse]:
        return self.warehouses.get(warehouse_id)
    
    def get_vehicle(self, vehicle_id: str) -> Optional[Transport]:
        return self.vehicles.get(vehicle_id)

    def get_courier_type(self, courier: Transport) -> Optional[CourierType]:
        return self.courier_types.get(courier.courier_type_id)
    
    def get_route(self, route_id: str) -> Optional[Route]:
        return self.routes.get(route_id)
    
    def get_pending_orders(self) -> List[Order]:
        return [o for o in self.orders.values() if o.status == OrderStatus.PENDING]
    
    def get_available_vehicles(self, warehouse_id: Optional[str] = None) -> List[Transport]:
        vehicles = [v for v in self.vehicles.values() if v.is_available()]
        if warehouse_id:
            vehicles = [v for v in vehicles if getattr(v, 'warehouse_id', None) == warehouse_id]
        return vehicles
    
    def save_state(self, timestamp: datetime) -> None:
        state = {
            "timestamp": timestamp.isoformat(),
            "orders_count": len(self.orders),
            "pending_orders": len(self.get_pending_orders()),
            "vehicles_count": len(self.vehicles),
            "available_vehicles": len(self.get_available_vehicles()),
            "routes_count": len(self.routes),
        }
        self.history.append(state)
    
    def get_metrics(self) -> dict:
        if not self.history:
            return {}
        
        delivered_orders = sum(1 for o in self.orders.values() if o.status == OrderStatus.DELIVERED)
        total_orders = len(self.orders)
        
        return {
            "total_orders": total_orders,
            "delivered_orders": delivered_orders,
            "delivery_rate": delivered_orders / total_orders if total_orders > 0 else 0,
            "pending_orders": len(self.get_pending_orders()),
            "total_vehicles": len(self.vehicles),
            "available_vehicles": len(self.get_available_vehicles()),
            "total_routes": len(self.routes),
            "simulation_steps": len(self.history),
        }


class SimulationController:
    def __init__(self, start_time: datetime, time_step_minutes: int = 1):
        self.time_manager = TimeManager(start_time, time_step_minutes)
        self.event_manager = EventManager()
        self.state_manager = StateManager()
        self.is_running = False
        self.max_steps: Optional[int] = None
    
    def initialize(self) -> None:
        """Initialize simulation with default setup"""
        self.event_manager.publish(Event(
            event_type=EventType.SIMULATION_STARTED,
            timestamp=self.time_manager.current_time,
            data={},
            entity_id="simulator"
        ))
    
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
        # This is where the main simulation logic would go
        # For now, it's a placeholder for future implementation
        pass
    
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
    
    def get_current_time(self) -> datetime:
        """Get current simulation time"""
        return self.time_manager.current_time
