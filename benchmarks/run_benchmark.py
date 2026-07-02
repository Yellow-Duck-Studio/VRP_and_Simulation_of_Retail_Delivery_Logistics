"""
benchmarks/run_benchmark.py

Reproducibility & Benchmarking entry point.

What this does, end to end:

1. Generates a synthetic task with explicitly obvious geographical
   clusters (North / South orders, see `synthetic_data.py`).
2. For each algorithm, strictly locks `random.seed(SEED)` right before
   that algorithm runs - so every algorithm starts from the exact same
   RNG state and the whole run is bit-for-bit reproducible.
3. Runs SWEEP, CLWR (Clarke-Wright) and DBSCAN in evolutionary mode,
   plus the naive RND baseline, via the existing
   `run_evolutionary_clustering`.
4. Tracks `valid_clusterizations_archive` size + best fitness on every
   single generation (not just every 100, like the console log does)
   via the `on_generation` callback, and writes that progression to
   `archive_progression.csv`.
5. Builds and prints a reporting table comparing the final
   `fitness_score` of SWEEP / CLWR / DBSCAN against the RND baseline,
   and saves it to `report.md`.

Run from the project root (same place you'd run `python main.py`):

    python -m benchmarks.run_benchmark
    python -m benchmarks.run_benchmark --generations 300 --seed 42
    
"""

from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from benchmarks.synthetic_data import generate_synthetic_task
from evolutionary_algorithm.algorithm import run_evolutionary_clustering
from evolutionary_algorithm.domain import Algorithms, Constraint, Individual
from evolutionary_algorithm.fitness_registry import resolve_fitness_config
from evolutionary_algorithm.parser import load_transport_constraints

DEFAULT_SEED = 42

# RND is run first and used as the naive baseline everything else is
# measured against, per the requirement.
BENCHMARK_ALGORITHMS = [
    ("RND", Algorithms.RND),
    ("SWEEP", Algorithms.SWEEP),
    ("CLWR", Algorithms.CLWR),
    ("DBSCAN", Algorithms.DBSCAN),
]


@dataclass
class GenerationRecord:
    algorithm: str
    generation: int
    best_fitness: float
    archive_size: int


@dataclass
class AlgorithmResult:
    algorithm: str
    best_fitness: Optional[float]
    avg_fitness: Optional[float]
    valid_count: int
    total_count: int
    delta_vs_baseline_pct: Optional[float]


def _build_constraints(data_dir: Path) -> Constraint:
    """Mirrors experiments/runner.py::_build_constraints - vehicle
    constraints are universal (not task-specific), so we keep reading
    them from the real transport_types.csv even though orders/
    warehouses are synthetic."""
    speeds, max_payloads, *_ = load_transport_constraints(str(data_dir / "transport_types.csv"))
    return Constraint(
        max_order_count=5,
        max_weight_per_transport=max_payloads,
        speeds_kmh=speeds,
        transport_distribution={"car": 0.80, "bike": 0.15, "foot": 0.05},
    )


def run_single_algorithm(
    label: str,
    algorithm: Algorithms,
    orders,
    warehouses_dict,
    constraints: Constraint,
    generations: int,
    population_size: int,
    fitness_config,
    seed: int,
    history: List[GenerationRecord],
) -> List[Individual]:
    # Strictly lock the seed right before THIS algorithm runs. This is
    # what guarantees determinism: every algorithm sees the identical
    # RNG state at generation 0, so re-running the whole suite always
    # produces the same numbers, and no algorithm is advantaged or
    # disadvantaged by RNG state left over from the previous one.
    random.seed(seed)

    def on_generation(gen: int, best_fitness: float, archive_size: int) -> None:
        history.append(GenerationRecord(label, gen, best_fitness, archive_size))

    return run_evolutionary_clustering(
        algorithm=algorithm,
        orders=orders,
        warehouses_dict=warehouses_dict,
        constraints=constraints,
        generations=generations,
        population_size=population_size,
        fitness_config=fitness_config,
        on_generation=on_generation,
    )


def build_report(results: Dict[str, List[Individual]], baseline_label: str = "RND") -> List[AlgorithmResult]:
    summaries: Dict[str, AlgorithmResult] = {}

    for label, individuals in results.items():
        fitness_scores = [ind.fitness_score for ind in individuals if ind.fitness_score != float("inf")]
        valid_count = sum(1 for ind in individuals if ind.is_valid)
        best = min(fitness_scores) if fitness_scores else None
        avg = (sum(fitness_scores) / len(fitness_scores)) if fitness_scores else None
        summaries[label] = AlgorithmResult(
            algorithm=label,
            best_fitness=best,
            avg_fitness=avg,
            valid_count=valid_count,
            total_count=len(individuals),
            delta_vs_baseline_pct=None,
        )

    baseline = summaries.get(baseline_label)
    if baseline and baseline.best_fitness:
        for label, summary in list(summaries.items()):
            if label == baseline_label or summary.best_fitness is None:
                continue
            delta = (summary.best_fitness - baseline.best_fitness) / baseline.best_fitness * 100
            summaries[label] = AlgorithmResult(
                algorithm=summary.algorithm,
                best_fitness=summary.best_fitness,
                avg_fitness=summary.avg_fitness,
                valid_count=summary.valid_count,
                total_count=summary.total_count,
                delta_vs_baseline_pct=delta,
            )

    ordered_labels = [baseline_label] + [label for label, _ in BENCHMARK_ALGORITHMS if label != baseline_label]
    return [summaries[label] for label in ordered_labels if label in summaries]


def render_report_table(report: List[AlgorithmResult]) -> str:
    header = (
        f"| {'Algorithm':<10} | {'Best Fitness':>14} | {'Avg Fitness':>14} "
        f"| {'Valid/Total':>12} | {'Δ vs RND':>10} |"
    )
    sep = "|" + "-" * 12 + "|" + "-" * 16 + "|" + "-" * 16 + "|" + "-" * 14 + "|" + "-" * 12 + "|"
    lines = [header, sep]
    for r in report:
        best = f"{r.best_fitness:.2f}" if r.best_fitness is not None else "N/A"
        avg = f"{r.avg_fitness:.2f}" if r.avg_fitness is not None else "N/A"
        valid_total = f"{r.valid_count}/{r.total_count}"
        if r.delta_vs_baseline_pct is None:
            delta = "baseline" if r.algorithm == "RND" else "N/A"
        else:
            delta = f"{r.delta_vs_baseline_pct:+.1f}%"
        lines.append(
            f"| {r.algorithm:<10} | {best:>14} | {avg:>14} | {valid_total:>12} | {delta:>10} |"
        )
    return "\n".join(lines)


def save_history_csv(history: List[GenerationRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["algorithm", "generation", "best_fitness", "archive_size"])
        writer.writeheader()
        for r in history:
            writer.writerow({
                "algorithm": r.algorithm,
                "generation": r.generation,
                "best_fitness": r.best_fitness,
                "archive_size": r.archive_size,
            })


def print_archive_growth_summary(history: List[GenerationRecord], generations: int) -> None:
    """Sanity-check printout: confirms the archive is actively growing
    (not stuck at 0) for each algorithm, sampled at a few checkpoints."""
    checkpoints = sorted({0, generations // 4, generations // 2, (3 * generations) // 4, generations - 1})
    by_algo: Dict[str, Dict[int, GenerationRecord]] = {}
    for r in history:
        by_algo.setdefault(r.algorithm, {})[r.generation] = r

    print("\nArchive growth checkpoints (valid_clusterizations_archive size):")
    header = f"  {'Algorithm':<10} | " + " | ".join(f"gen {c:>4}" for c in checkpoints)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for label, _ in BENCHMARK_ALGORITHMS:
        records = by_algo.get(label, {})
        row = f"  {label:<10} | " + " | ".join(
            f"{records[c].archive_size:>7}" if c in records else f"{'--':>7}"
            for c in checkpoints
        )
        print(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproducibility & benchmarking suite")
    parser.add_argument("--generations", type=int, default=300)
    parser.add_argument("--population-size", type=int, default=50)
    parser.add_argument("--fitness-version", default="business_v1")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    constraints = _build_constraints(data_dir)
    fitness_config = resolve_fitness_config(args.fitness_version)

    dataset = generate_synthetic_task(task_id="synthetic_north_south", seed=args.seed)
    print(
        f"Synthetic dataset: {len(dataset.orders)} orders across "
        f"{len(dataset.clusters)} geo-clusters, {len(dataset.warehouses)} warehouse(s), "
        f"task_id={dataset.task_id}"
    )
    for cluster in dataset.clusters:
        print(f"  - {cluster.name}: center=({cluster.center_lat}, {cluster.center_lon}), "
              f"n_orders={cluster.n_orders}, jitter={cluster.jitter_deg} deg")

    history: List[GenerationRecord] = []
    results: Dict[str, List[Individual]] = {}

    for label, algorithm in BENCHMARK_ALGORITHMS:
        print(f"\nRunning {label} (seed locked to {args.seed}, {args.generations} generations)...")
        individuals = run_single_algorithm(
            label=label,
            algorithm=algorithm,
            orders=dataset.orders,
            warehouses_dict=dataset.warehouses,
            constraints=constraints,
            generations=args.generations,
            population_size=args.population_size,
            fitness_config=fitness_config,
            seed=args.seed,
            history=history,
        )
        results[label] = individuals
        print(f"  -> {len(individuals)} valid clusterizations archived")

    report = build_report(results, baseline_label="RND")

    print("\n" + "=" * 78)
    print("REPRODUCIBILITY & BENCHMARKING REPORT")
    print("=" * 78)
    table = render_report_table(report)
    print(table)

    print_archive_growth_summary(history, args.generations)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = data_dir / "benchmarks" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "report.md").write_text(table, encoding="utf-8")
    save_history_csv(history, out_dir / "archive_progression.csv")

    print(f"\nSaved report to:       {out_dir / 'report.md'}")
    print(f"Saved archive history: {out_dir / 'archive_progression.csv'}")


if __name__ == "__main__":
    main()
