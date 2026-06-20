from __future__ import annotations

from pipeline.fitness import evaluate_fitness
from pipeline.types import MetricsResult, Solution, TaskContext


def evaluate_solution_metrics(
    solution: Solution,
    task_context: TaskContext,
    metrics_config: dict | None = None,
) -> MetricsResult:
    fitness = evaluate_fitness(solution, task_context, metrics_config)

    return MetricsResult(
        is_valid=fitness.is_valid,
        fitness_score=fitness.fitness_score,
        t_total_hours=fitness.t_total_hours,
        p_hard=fitness.p_hard,
        p_capacity=fitness.p_capacity,
        p_mass=fitness.p_mass,
        p_sla=fitness.p_sla,
        p_sync=fitness.p_sync,
        p_fleet=fitness.p_fleet,
        p_direction=fitness.p_direction,
        trip_count=fitness.trip_count,
        total_distance_km=fitness.total_distance_km,
        total_travel_time_hours=fitness.t_total_hours,
        late_orders_count=fitness.late_orders_count,
        total_lateness_minutes=fitness.total_lateness_minutes,
        max_lateness_minutes=fitness.max_lateness_minutes,
        avg_orders_per_trip=fitness.avg_orders_per_trip,
        total_orders=fitness.total_orders,
    )


def summarize_solutions(solutions: list[Solution]) -> dict[str, float | int | None]:
    valid_solutions = [solution for solution in solutions if solution.metrics.is_valid]
    best_solution = min(valid_solutions, key=lambda item: item.metrics.fitness_score) if valid_solutions else None

    return {
        "total_solutions": len(solutions),
        "valid_solutions": len(valid_solutions),
        "best_fitness_score": best_solution.metrics.fitness_score if best_solution else None,
        "best_solution_id": best_solution.solution_id if best_solution else None,
    }
