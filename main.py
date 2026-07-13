from evolutionary_algorithm.parser import load_all_orders, load_all_warehouses, load_transport_constraints
from evolutionary_algorithm.domain import Constraint, Algorithms
from evolutionary_algorithm.algorithm import run_evolutionary_clustering
from evolutionary_algorithm.fitness_registry import resolve_fitness_config
from evolutionary_algorithm.evaluation import build_fitness_fn
from clusterization_logger import save_clusterizations
from experiments.publish import publish_algorithm_run
from experiments.runner import run_experiment_suite
from experiments.types import ExperimentConfig
from stats.clusterization_metrics import print_archive_stats
import argparse
from pathlib import Path


def _build_fee_table(fixed_fee, per_km_fee, per_order_fee, per_kg_min_fee) -> dict:
    transport_types = set(fixed_fee) | set(per_km_fee) | set(per_order_fee) | set(per_kg_min_fee)
    return {
        t: {
            "fixed_fee":      fixed_fee.get(t, 0.0),
            "per_km_fee":     per_km_fee.get(t, 0.0),
            "per_order_fee":  per_order_fee.get(t, 0.0),
            "per_kg_min_fee": per_kg_min_fee.get(t, 0.0),
        }
        for t in transport_types
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "target",
        nargs="?",
        help="Algorithm for a legacy single run, or one of: experiment, publish",
    )
    parser.add_argument("--algorithms", nargs="+")
    parser.add_argument("--execution-mode", default=None, choices=["standalone", "evolutionary"])
    parser.add_argument("--fitness-version", default="business_v1")
    parser.add_argument("--fitness-function", default="time", choices=["time", "economics"],
        help="Which fitness function to use: 'time' (evaluate_fitness) or 'economics' (evaluate_fitness_economics).",
    )
    parser.add_argument("--label", default="manual_run")
    parser.add_argument("--generations", type=int, default=500)
    parser.add_argument("--population-size", type=int, default=50)
    parser.add_argument("--run-id")
    parser.add_argument("--algorithm")
    args = parser.parse_args()

    data_dir = Path("data")

    if args.target == "experiment":
        if not args.algorithms:
            parser.error("--algorithms is required for experiment mode.")
        manifest = run_experiment_suite(
            ExperimentConfig(
                algorithms=args.algorithms,
                execution_mode=args.execution_mode or "standalone",
                fitness_version=args.fitness_version,
                generations=args.generations,
                population_size=args.population_size,
                label=args.label,
            ),
            data_dir=data_dir,
            runs_dir=data_dir / "runs",
        )
        print(f"Experiment run created: {manifest.run_id}")
        print(f"Leaderboard: {data_dir / 'runs' / manifest.run_id / 'leaderboard.csv'}")
        return

    if args.target == "publish":
        if not args.run_id or not args.algorithm:
            parser.error("--run-id and --algorithm are required for publish mode.")
        target_json, target_csv, submission_path = publish_algorithm_run(
            run_root=data_dir / "runs" / args.run_id,
            algorithm_name=args.algorithm,
            data_dir=data_dir,
        )
        print("Published run successfully:")
        print(f"  JSON: {target_json}")
        print(f"  CSV:  {target_csv}")
        print(f"  Submission: {submission_path}")
        return

    if args.target is None:
        parser.error("Provide an algorithm for a single run or use 'experiment'/'publish'.")

    try:
        selected_algorithm = Algorithms[args.target.upper()]
    except KeyError as error:
        raise SystemExit(f"Unknown target '{args.target}'. Use an algorithm name or 'experiment'/'publish'.") from error

    execution_mode = args.execution_mode or "evolutionary"

    print("Loading comprehensive datasets...")

    tasks_orders     = load_all_orders('data/small/orders.csv')
    tasks_warehouses = load_all_warehouses('data/small/warehouses.csv')
    speeds, max_payloads, fixed_fee, per_km_fee, per_order_fee, per_kg_min_fee \
        = load_transport_constraints('data/transport_types.csv')

    fee_table = _build_fee_table(fixed_fee, per_km_fee, per_order_fee, per_kg_min_fee)

    # Define universal constraints for all tasks
    constraints = Constraint(
        max_order_count=5,
        max_weight_per_transport=max_payloads,
        speeds_kmh=speeds,
        transport_distribution={'car': 0.80, 'bike': 0.15, 'foot': 0.05}
    )

    # This will hold the final structured JSON data
    master_archive = {}


    # Собираем fitness_fn один раз — он одинаковый для всех task_id
    fitness_fn = build_fitness_fn(
        mode=args.fitness_function,
        fitness_config=resolve_fitness_config(args.fitness_version),
    )

    # 2. Iterate through every isolated polygon (task)
    for task_id, isolated_orders in tasks_orders.items():
        print(f"\n" + "=" * 45)
        print(f" RUNNING EVOLUTION FOR TASK ID: {task_id}")
        print("=" * 45)

        # Fetch the specific warehouses for this task
        isolated_warehouses = tasks_warehouses.get(task_id, {})

        print(f"Loaded {len(isolated_orders)} orders across {len(isolated_warehouses)} warehouses.")

        if execution_mode == "standalone":
            from experiments.standalone import run_standalone_algorithm

            reverse_registry = {
                Algorithms.DBSCAN: "dbscan",
                Algorithms.SWEEP: "sweep",
                Algorithms.CLWR: "clarke_wright",
                Algorithms.DSTR: "destroy_repair",
                Algorithms.RND: "random",
            }

            valid_individuals = run_standalone_algorithm(
                algorithm_name=reverse_registry[selected_algorithm],
                orders=isolated_orders,
                warehouses_dict=isolated_warehouses,
                constraints=constraints,
                population_size=args.population_size,
                fitness_fn=fitness_fn,  # <-- было fitness_config=resolve_fitness_config(...)
            )
        else:
            valid_individuals = run_evolutionary_clustering(
                algorithm=selected_algorithm,
                orders=isolated_orders,
                warehouses_dict=isolated_warehouses,
                constraints=constraints,
                generations=args.generations,
                population_size=args.population_size,
                fitness_fn=fitness_fn,  # <-- было fitness_config=resolve_fitness_config(...)
            )

        master_archive[f"task_{task_id}"] = valid_individuals
        print(f"Successfully archived {len(valid_individuals)} unique combinations.")

    # Сохранение результатов (без стоимостей)
    json_path, csv_path = save_clusterizations(master_archive, "data/master_clusterizations")
    print(f"\nDone! Results saved to:")
    print(f"  JSON: {json_path}")
    print(f"  CSV:  {csv_path}")

    # Статистика стоимостей
    print_archive_stats(
        master_archive=master_archive,
        tasks_orders=tasks_orders,
        tasks_warehouses=tasks_warehouses,
        fee_table=fee_table,
    )


if __name__ == "__main__":
    main()