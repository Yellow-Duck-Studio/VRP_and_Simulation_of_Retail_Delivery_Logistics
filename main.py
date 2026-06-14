from evolutionary_algorithm.parser import load_orders, load_warehouses, load_transport_constraints
from evolutionary_algorithm.domain import Constraint
from evolutionary_algorithm.algorithm import run_evolutionary_clustering


def main():
    print("Loading data...")
    orders = load_orders('data/enriched_orders 2.csv')
    warehouses = load_warehouses('data/enriched_warehouses 2.csv')
    speeds, max_payloads = load_transport_constraints('data/transport_types.csv')

    # 1. Define the Constraints based on task requirements
    constraints = Constraint(
        max_order_count=5,  # You can adjust this threshold [cite: 24, 25, 26]
        max_weight_per_transport=max_payloads,  # Sourced from transport_types.csv
        speeds_kmh=speeds,  # Sourced from transport_types.csv

        # Mapping standard distribution (e.g., 80% car, 15% bike, 5% foot) [cite: 22]
        # Note: transport_types.csv uses 'bike', 'foot', 'car'
        transport_distribution={'car': 0.80, 'bike': 0.15, 'foot': 0.05}
    )

    print(f"Loaded {len(orders)} orders across {len(warehouses)} warehouses.")
    print("Starting Evolutionary Algorithm...")

    # 2. Run the algorithm
    # Using smaller numbers here for a quick test run.
    # For production, increase generations to 1000+ and population to 100+
    valid_clusters = run_evolutionary_clustering(
        orders=orders,
        warehouses_dict=warehouses,
        constraints=constraints,
        generations=1000,
        population_size=50
    )

    # 3. Output Results
    print("\n--- Evolution Complete ---")
    print(f"Total unique, valid clusterizations generated: {len(valid_clusters)}")

    # Optional: Inspect the first valid solution found
    if valid_clusters:
        sample_solution = list(valid_clusters)[0]
        print(f"\nSample Trip Distribution (Set of Sets):")
        for trip in sample_solution:
            print(f"  Trip Orders: {list(trip)}")


if __name__ == "__main__":
    main()