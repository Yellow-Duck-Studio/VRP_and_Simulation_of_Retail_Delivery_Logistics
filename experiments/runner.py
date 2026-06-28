from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from clusterization_logger import save_clusterizations
from evolutionary_algorithm.algorithm import run_evolutionary_clustering
from evolutionary_algorithm.domain import Constraint
from evolutionary_algorithm.fitness_registry import resolve_fitness_config
from evolutionary_algorithm.parser import load_all_orders, load_all_warehouses, load_transport_constraints
from experiments.registry import resolve_algorithm
from experiments.standalone import run_standalone_algorithm
from experiments.types import AlgorithmSummary, ExperimentConfig, ExperimentRunManifest


def _build_constraints(data_dir: Path) -> Constraint:
    speeds, max_payloads, *_ = load_transport_constraints(str(data_dir / "transport_types.csv"))
    return Constraint(
        max_order_count=5,
        max_weight_per_transport=max_payloads,
        speeds_kmh=speeds,
        transport_distribution={"car": 0.80, "bike": 0.15, "foot": 0.05},
    )


def _aggregate_algorithm_summary(master_archive: dict[str, list]) -> tuple[int, int, float | None, float | None]:
    total_clusterizations = 0
    valid_clusterizations = 0
    fitness_scores: list[float] = []

    for individuals in master_archive.values():
        total_clusterizations += len(individuals)
        for individual in individuals:
            if individual.is_valid:
                valid_clusterizations += 1
            if individual.fitness_score != float("inf"):
                fitness_scores.append(individual.fitness_score)

    if not fitness_scores:
        return total_clusterizations, valid_clusterizations, None, None

    return (
        total_clusterizations,
        valid_clusterizations,
        min(fitness_scores),
        sum(fitness_scores) / len(fitness_scores),
    )


def _count_invalid_reasons(individuals: list) -> dict[str, int]:
    counts = {"capacity": 0, "mass": 0, "sla": 0}
    for individual in individuals:
        for reason, is_present in getattr(individual, "invalid_reasons", {}).items():
            if is_present:
                counts[reason] += 1
    return counts


def _save_leaderboard(manifest: ExperimentRunManifest, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "run_id",
                "label",
                "algorithm",
                "fitness_version",
                "total_tasks",
                "total_clusterizations",
                "valid_clusterizations",
                "best_fitness_score",
                "average_fitness_score",
                "output_json",
                "output_csv",
            ],
        )
        writer.writeheader()
        for summary in manifest.summaries:
            writer.writerow(
                {
                    "run_id": manifest.run_id,
                    "label": manifest.label,
                    "algorithm": summary.algorithm,
                    "fitness_version": manifest.fitness_version,
                    "total_tasks": summary.total_tasks,
                    "total_clusterizations": summary.total_clusterizations,
                    "valid_clusterizations": summary.valid_clusterizations,
                    "best_fitness_score": summary.best_fitness_score,
                    "average_fitness_score": summary.average_fitness_score,
                    "output_json": summary.output_json,
                    "output_csv": summary.output_csv,
                }
            )


def run_experiment_suite(
    config: ExperimentConfig,
    data_dir: Path,
    runs_dir: Path,
) -> ExperimentRunManifest:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = runs_dir / run_id
    tasks_orders = load_all_orders(str(data_dir / "orders.csv"))
    tasks_warehouses = load_all_warehouses(str(data_dir / "warehouses.csv"))
    constraints = _build_constraints(data_dir)
    fitness_config = resolve_fitness_config(config.fitness_version, config.fitness_overrides)

    print(f"Starting experiment run: {run_id}")
    print(f"Label: {config.label}")
    print(f"Mode: {config.execution_mode}")
    print(f"Fitness: {fitness_config.version}")
    print(f"Algorithms: {', '.join(config.algorithms)}")
    print(f"Tasks: {len(tasks_orders)}")
    print(f"Output directory: {run_root}")

    summaries: list[AlgorithmSummary] = []

    for algorithm_index, algorithm_name in enumerate(config.algorithms, start=1):
        print(f"\n[{algorithm_index}/{len(config.algorithms)}] Running algorithm: {algorithm_name}")
        master_archive = {}

        for task_index, (task_id, isolated_orders) in enumerate(tasks_orders.items(), start=1):
            isolated_warehouses = tasks_warehouses.get(task_id, {})
            print(
                f"  - Task {task_id} ({task_index}/{len(tasks_orders)}): "
                f"{len(isolated_orders)} orders, {len(isolated_warehouses)} warehouses"
            )
            if config.execution_mode == "standalone":
                individuals = run_standalone_algorithm(
                    algorithm_name=algorithm_name,
                    orders=isolated_orders,
                    warehouses_dict=isolated_warehouses,
                    constraints=constraints,
                    population_size=config.population_size,
                    fitness_config=fitness_config,
                )
            elif config.execution_mode == "evolutionary":
                algorithm_enum = resolve_algorithm(algorithm_name)
                individuals = run_evolutionary_clustering(
                    algorithm=algorithm_enum,
                    orders=isolated_orders,
                    warehouses_dict=isolated_warehouses,
                    constraints=constraints,
                    generations=config.generations,
                    population_size=config.population_size,
                    fitness_config=fitness_config,
                )
            else:
                raise ValueError(f"Unknown execution mode: {config.execution_mode}")

            master_archive[f"task_{task_id}"] = list(individuals)
            valid_count = sum(1 for individual in individuals if individual.is_valid)
            invalid_reason_counts = _count_invalid_reasons(individuals)
            print(
                f"    Completed task {task_id}: "
                f"{len(individuals)} solutions, {valid_count} valid, "
                f"invalid_by_sla={invalid_reason_counts['sla']}, "
                f"invalid_by_mass={invalid_reason_counts['mass']}, "
                f"invalid_by_capacity={invalid_reason_counts['capacity']}"
            )

        algorithm_dir = run_root / algorithm_name
        json_path, csv_path = save_clusterizations(master_archive, str(algorithm_dir / "master_clusterizations"))
        total_clusterizations, valid_clusterizations, best_fitness, avg_fitness = _aggregate_algorithm_summary(master_archive)

        summaries.append(
            AlgorithmSummary(
                algorithm=algorithm_name,
                total_tasks=len(tasks_orders),
                total_clusterizations=total_clusterizations,
                valid_clusterizations=valid_clusterizations,
                best_fitness_score=best_fitness,
                average_fitness_score=avg_fitness,
                output_json=str(json_path),
                output_csv=str(csv_path),
            )
        )
        print(
            f"  Saved {algorithm_name}: "
            f"{total_clusterizations} solutions total, "
            f"{valid_clusterizations} valid, "
            f"best fitness={best_fitness}"
        )

    manifest = ExperimentRunManifest(
        run_id=run_id,
        label=config.label,
        execution_mode=config.execution_mode,
        fitness_version=config.fitness_version,
        fitness_overrides=config.fitness_overrides,
        generations=config.generations,
        population_size=config.population_size,
        algorithms=list(config.algorithms),
        summaries=summaries,
        metadata={
            "data_dir": str(data_dir),
            "run_root": str(run_root),
        },
    )

    run_root.mkdir(parents=True, exist_ok=True)
    manifest_path = run_root / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as file:
        json.dump(asdict(manifest), file, ensure_ascii=False, indent=2)

    _save_leaderboard(manifest, run_root / "leaderboard.csv")
    with (run_root / "leaderboard.json").open("w", encoding="utf-8") as file:
        json.dump([asdict(summary) for summary in summaries], file, ensure_ascii=False, indent=2)

    print("\nExperiment finished.")
    print(f"Manifest: {manifest_path}")
    print(f"Leaderboard CSV: {run_root / 'leaderboard.csv'}")

    return manifest
