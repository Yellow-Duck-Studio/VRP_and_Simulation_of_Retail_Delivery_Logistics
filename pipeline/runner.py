from __future__ import annotations

from typing import Callable, Dict, List

from heuristics.clarke_wright import run_clarke_wright
from heuristics.destroy_repair import run_destroy_repair_improver
from heuristics.trivial_initializer import run_trivial_initializer
from pipeline.config import validate_pipeline_config
from pipeline.metrics import evaluate_solution_metrics, summarize_solutions
from pipeline.types import PipelineConfig, PipelineRunResult, Solution, TaskContext


InitializerFn = Callable[[TaskContext, dict], List[Solution]]
ImproverFn = Callable[[TaskContext, List[Solution], dict], List[Solution]]


INITIALIZERS: Dict[str, InitializerFn] = {
    "clarke_wright": run_clarke_wright,
    "trivial": run_trivial_initializer,
}

IMPROVERS: Dict[str, ImproverFn] = {
    "destroy_repair": run_destroy_repair_improver,
}


def run_pipeline(task_context: TaskContext, config: PipelineConfig) -> PipelineRunResult:
    validate_pipeline_config(config)

    initializer = INITIALIZERS[config.initializer]
    stage_names = [config.initializer]
    solutions = initializer(task_context, config.initializer_config)

    if config.improver:
        improver = IMPROVERS[config.improver]
        stage_names.append(config.improver)
        solutions = improver(task_context, solutions, config.improver_config)

    evaluated_solutions = []
    for solution in solutions[: config.max_solutions]:
        solution.metrics = evaluate_solution_metrics(solution, task_context, config.metrics_config)
        evaluated_solutions.append(solution)

    evaluated_solutions.sort(key=lambda item: item.metrics.fitness_score)

    pipeline_name = "_then_".join(stage_names)
    return PipelineRunResult(
        task_id=task_context.task_id,
        pipeline_name=pipeline_name,
        config=config,
        solutions=evaluated_solutions,
        summary=summarize_solutions(evaluated_solutions),
    )
