from datetime import datetime
from typing import List, Optional, Dict
from ..schemas import Courier, CourierType, Route, Warehouse, Order, OrderStatus, DistanceMatrix

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