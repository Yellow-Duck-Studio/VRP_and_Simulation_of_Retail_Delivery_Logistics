from evolutionary_algorithm.parser import load_all_orders, load_all_warehouses, load_transport_constraints
from evolutionary_algorithm.domain import Constraint, Algorithms
from evolutionary_algorithm.algorithm import run_evolutionary_clustering
from clusterization_logger import save_clusterizations
from clusterization_metrics import print_archive_stats
import argparse


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
        "algorithm",
        type=lambda a: Algorithms[a.upper()],
        choices=list(Algorithms),
        help="Choose an algorithm to start with"
    )
    args = parser.parse_args()
    print("Loading comprehensive datasets...")

    tasks_orders     = load_all_orders('data/orders.csv')
    tasks_warehouses = load_all_warehouses('data/warehouses.csv')
    speeds, max_payloads, fixed_fee, per_km_fee, per_order_fee, per_kg_min_fee \
        = load_transport_constraints('data/transport_types.csv')

    fee_table = _build_fee_table(fixed_fee, per_km_fee, per_order_fee, per_kg_min_fee)

    constraints = Constraint(
        max_order_count=5,
        max_weight_per_transport=max_payloads,
        speeds_kmh=speeds,
        transport_distribution={'car': 0.80, 'bike': 0.15, 'foot': 0.05}
    )

    master_archive = {}

    for task_id, isolated_orders in tasks_orders.items():
        print(f"\n{'=' * 45}")
        print(f" RUNNING EVOLUTION FOR TASK ID: {task_id}")
        print("=" * 45)

        isolated_warehouses = tasks_warehouses.get(task_id, {})
        print(f"Loaded {len(isolated_orders)} orders across {len(isolated_warehouses)} warehouses.")

        valid_individuals = run_evolutionary_clustering(
            algorithm=args.algorithm,
            orders=isolated_orders,
            warehouses_dict=isolated_warehouses,
            constraints=constraints,
            generations=500,
            population_size=50,
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