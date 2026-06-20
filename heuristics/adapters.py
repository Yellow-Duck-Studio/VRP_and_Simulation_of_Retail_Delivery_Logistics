from __future__ import annotations

from evolutionary_algorithm.domain import Constraint, Individual, Order, Trip
from pipeline.types import ConstraintData, Solution, TaskContext, TripResult


def to_domain_constraint(constraint: ConstraintData) -> Constraint:
    return Constraint(
        max_order_count=constraint.max_order_count,
        max_weight_per_transport=constraint.max_weight_per_transport,
        speeds_kmh=constraint.speeds_kmh,
        transport_distribution=constraint.transport_distribution,
    )


def to_domain_orders(task_context: TaskContext) -> list[Order]:
    return [
        Order(
            order_id=order.order_id,
            warehouse_id=order.warehouse_id,
            lat=order.lat,
            lon=order.lon,
            pickup_ready_at=order.pickup_ready_at,
            delivery_deadline_at=order.delivery_deadline_at,
            total_mass_kg=order.total_mass_kg,
        )
        for order in task_context.orders
    ]


def individual_to_solution(
    individual: Individual,
    task_context: TaskContext,
    pipeline: list[str],
    source_stage: str,
    solution_index: int,
    metadata: dict | None = None,
) -> Solution:
    trips = []
    for trip in sorted(individual.trips.values(), key=lambda item: item.trip_id):
        if not trip.order_ids:
            continue
        trips.append(
            TripResult(
                trip_id=trip.trip_id,
                warehouse_id=trip.warehouse_id,
                transport_type=trip.transport_type,
                order_ids=sorted(trip.order_ids),
            )
        )

    return Solution(
        solution_id=f"task_{task_context.task_id}_{source_stage}_{solution_index:03d}",
        pipeline=list(pipeline),
        source_stage=source_stage,
        trips=trips,
        metrics=None,  # type: ignore[arg-type]
        metadata=metadata or {},
    )


def solution_to_individual(solution: Solution) -> Individual:
    individual = Individual()
    for trip in solution.trips:
        individual.trips[trip.trip_id] = Trip(
            trip_id=trip.trip_id,
            warehouse_id=trip.warehouse_id,
            transport_type=trip.transport_type,
            order_ids=list(trip.order_ids),
        )
    return individual
