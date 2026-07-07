from __future__ import annotations

from pipeline.types import Solution, TaskContext, TripResult


def run_trivial_initializer(task_context: TaskContext, config: dict) -> list[Solution]:
    default_transport = config.get(
        "default_transport_type",
        max(task_context.constraints.speeds_kmh, key=task_context.constraints.speeds_kmh.get),
    )

    trips = []
    for trip_id, order in enumerate(task_context.orders, start=1):
        trips.append(
            TripResult(
                trip_id=trip_id,
                warehouse_id=order.warehouse_id,
                transport_type=default_transport,
                order_ids=[order.order_id],
            )
        )

    return [
        Solution(
            solution_id=f"task_{task_context.task_id}_trivial_001",
            pipeline=["trivial"],
            source_stage="trivial",
            trips=trips,
            metrics=None,  # type: ignore[arg-type]
            metadata={"initializer_config": config},
        )
    ]
