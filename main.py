import json
from evolutionary_algorithm.parser import load_all_orders, load_all_warehouses, load_transport_constraints
from evolutionary_algorithm.domain import Constraint, Algorithms
from evolutionary_algorithm.algorithm import run_evolutionary_clustering, Algorithms
import argparse


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "algorithm",
        type=lambda a: Algorithms[a.upper()],  # Maps string to Enum member (case-insensitive)
        choices=list(Algorithms),            # Restricts CLI choices to the Enum members
        help="Choose an algorithm to start with"
    )
    args = parser.parse_args()
    print("Loading comprehensive datasets...")

    # 1. Load data automatically grouped by task_id
    tasks_orders = load_all_orders('data/orders.csv')
    tasks_warehouses = load_all_warehouses('data/warehouses.csv')
    speeds, max_payloads, fixed_fee, per_km_fee, per_order_fee, per_kg_min_fee\
        = load_transport_constraints('data/transport_types.csv')

    # Define universal constraints for all tasks
    constraints = Constraint(
        max_order_count=5,
        max_weight_per_transport=max_payloads,
        speeds_kmh=speeds,
        transport_distribution={'car': 0.80, 'bike': 0.15, 'foot': 0.05}
    )

    # This will hold the final structured JSON data
    master_archive = {}

    # 2. Iterate through every isolated polygon (task)
    for task_id, isolated_orders in tasks_orders.items():
        print(f"\n" + "=" * 45)
        print(f" RUNNING EVOLUTION FOR TASK ID: {task_id}")
        print("=" * 45)

        # Fetch the specific warehouses for this task
        isolated_warehouses = tasks_warehouses.get(task_id, {})

        print(f"Loaded {len(isolated_orders)} orders across {len(isolated_warehouses)} warehouses.")

        # 3. Run the evolutionary algorithm
        valid_clusters = run_evolutionary_clustering(
            algorithm=args.algorithm,
            orders=isolated_orders,
            warehouses_dict=isolated_warehouses,
            constraints=constraints,
            generations=500,  # Increase this for production
            population_size=50  # Increase this for production
        )

        # 4. Serialize the output: Convert Sets/Frozensets to standard Python Lists
        serializable_solutions = []
        for configuration in valid_clusters:
            # Each 'configuration' is a valid way to route the entire task
            trip_list = [list(trip) for trip in configuration]
            serializable_solutions.append(trip_list)

        # 5. Store under the explicit task key
        master_archive[f"task_{task_id}"] = serializable_solutions
        print(f"Successfully archived {len(serializable_solutions)} unique combinations.")

    # 6. Save the explicitly mapped results to disk
    output_path = 'data/master_clusterizations.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(master_archive, f, indent=4)

    print(f"\nDone! All polygons optimized and safely stored in: {output_path}")


if __name__ == "__main__":
    main()
