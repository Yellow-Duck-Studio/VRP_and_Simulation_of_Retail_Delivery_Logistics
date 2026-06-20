from __future__ import annotations

from heuristics.adapters import (
    individual_to_solution,
    solution_to_individual,
    to_domain_constraint,
    to_domain_orders,
)
from heuristics.destroy_repair_core import run_destroy_repair
from pipeline.types import Solution, TaskContext


def run_destroy_repair_improver(
    task_context: TaskContext,
    seed_solutions: list[Solution],
    config: dict,
) -> list[Solution]:
    solutions = []
    iterations = config.get("iterations", 200)
    destroy_fraction = config.get("destroy_fraction", 0.2)
    max_solutions = config.get("max_solutions", 100)
    rng_seed = config.get("rng_seed", 42)

    for seed_index, seed_solution in enumerate(seed_solutions, start=1):
        seed_individual = solution_to_individual(seed_solution)
        improved_individuals = run_destroy_repair(
            seed_individual=seed_individual,
            orders=to_domain_orders(task_context),
            warehouses_dict=task_context.warehouses,
            constraints=to_domain_constraint(task_context.constraints),
            iterations=iterations,
            destroy_fraction=destroy_fraction,
            max_solutions=max_solutions,
            rng_seed=rng_seed,
        )

        for individual_index, individual in enumerate(improved_individuals, start=1):
            solutions.append(
                individual_to_solution(
                    individual=individual,
                    task_context=task_context,
                    pipeline=[*seed_solution.pipeline, "destroy_repair"],
                    source_stage="destroy_repair",
                    solution_index=(seed_index * 1000) + individual_index,
                    metadata={
                        "seed_solution_id": seed_solution.solution_id,
                        "improver_config": config,
                    },
                )
            )

    return solutions
