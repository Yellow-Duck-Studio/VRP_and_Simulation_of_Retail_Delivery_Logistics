from __future__ import annotations

from heuristics.adapters import individual_to_solution, to_domain_constraint, to_domain_orders
from heuristics.savings_core import build_clarke_wright_solution
from pipeline.types import Solution, TaskContext


def run_clarke_wright(task_context: TaskContext, config: dict) -> list[Solution]:
    individual = build_clarke_wright_solution(
        orders=to_domain_orders(task_context),
        warehouses_dict=task_context.warehouses,
        constraints=to_domain_constraint(task_context.constraints),
    )

    solution = individual_to_solution(
        individual=individual,
        task_context=task_context,
        pipeline=["clarke_wright"],
        source_stage="clarke_wright",
        solution_index=1,
        metadata={"initializer_config": config},
    )
    return [solution]
