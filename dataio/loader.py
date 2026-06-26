from __future__ import annotations

from pathlib import Path

from evolutionary_algorithm.parser import (
    load_all_orders,
    load_all_warehouses,
    load_transport_constraints,
)
from pipeline.types import ConstraintData, OrderData, TaskContext


def resolve_data_dir(base_dir: Path) -> Path:
    workspace_data_dir = base_dir.parent / "data"
    local_data_dir = base_dir / "data"

    if workspace_data_dir.exists():
        return workspace_data_dir
    return local_data_dir


def load_task_contexts(data_dir: Path) -> list[TaskContext]:
    tasks_orders = load_all_orders(str(data_dir / "orders.csv"))
    tasks_warehouses = load_all_warehouses(str(data_dir / "warehouses.csv"))
    speeds, max_payloads, fixed_fee, per_km_fee, per_order_fee, per_kg_min_fee\
        = load_transport_constraints(str(data_dir / "transport_types.csv"))

    constraints = ConstraintData(
        max_order_count=5,
        max_weight_per_transport=max_payloads,
        speeds_kmh=speeds,
        transport_distribution={"car": 0.80, "bike": 0.15, "foot": 0.05},
    )

    task_contexts = []
    for task_id, orders in tasks_orders.items():
        task_contexts.append(
            TaskContext(
                task_id=task_id,
                orders=[
                    OrderData(
                        order_id=order.order_id,
                        warehouse_id=order.warehouse_id,
                        lat=order.lat,
                        lon=order.lon,
                        pickup_ready_at=order.pickup_ready_at,
                        delivery_deadline_at=order.delivery_deadline_at,
                        total_mass_kg=order.total_mass_kg,
                    )
                    for order in orders
                ],
                warehouses=tasks_warehouses.get(task_id, {}),
                constraints=constraints,
            )
        )

    task_contexts.sort(key=lambda item: int(item.task_id))
    return task_contexts
