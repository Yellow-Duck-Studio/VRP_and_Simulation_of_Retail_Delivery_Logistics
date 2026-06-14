from typing import List, Dict, Tuple, Set

from evolutionary_algorithm.domain import Individual, Trip, Order, Constraint
import random

from evolutionary_algorithm.evaluation import evaluate_fitness


def mutate(individual: Individual, all_orders: List[Order]) -> Individual:
    """Randomly swaps an order to a different trip in the same warehouse."""
    new_ind = Individual(trips={k: Trip(**v.__dict__) for k, v in individual.trips.items()})

    active_trips = [t for t in new_ind.trips.values() if t.order_ids]
    if len(active_trips) < 2:
        return new_ind

    # Pick a random trip and an order to move
    source_trip = random.choice(active_trips)
    if not source_trip.order_ids: return new_ind

    order_id_to_move = random.choice(source_trip.order_ids)

    # Find valid target trips (same warehouse)
    target_trips = [t for t in active_trips if
                    t.warehouse_id == source_trip.warehouse_id and t.trip_id != source_trip.trip_id]

    if target_trips:
        target_trip = random.choice(target_trips)
        source_trip.order_ids.remove(order_id_to_move)
        target_trip.order_ids.append(order_id_to_move)

    return new_ind


def crossover(parent1: Individual, parent2: Individual) -> Individual:
    """
    Route-based Crossover: Takes a full valid trip from Parent 1 and injects it into Parent 2,
    resolving duplicate orders by removing them from Parent 2's other trips.
    """
    child = Individual(trips={k: Trip(**v.__dict__) for k, v in parent2.trips.items()})

    p1_active_trips = [t for t in parent1.trips.values() if t.order_ids]
    if not p1_active_trips: return child

    # Take a random trip block from parent 1
    injected_trip = random.choice(p1_active_trips)
    injected_order_ids = set(injected_trip.order_ids)

    # Clean up child: remove these orders from wherever they currently are
    for trip in child.trips.values():
        trip.order_ids = [oid for oid in trip.order_ids if oid not in injected_order_ids]

    # Add the newly injected trip
    new_trip_id = max(child.trips.keys()) + 1 if child.trips else 1
    child.trips[new_trip_id] = Trip(
        trip_id=new_trip_id,
        warehouse_id=injected_trip.warehouse_id,
        transport_type=injected_trip.transport_type,
        order_ids=list(injected_order_ids)
    )

    return child


def run_evolutionary_clustering(
        orders: List[Order],
        warehouses_dict: Dict[int, Tuple[float, float]],  # warehouse_id -> (lat, lon)
        constraints: Constraint,
        generations: int = 1000,
        population_size: int = 50
) -> Set[frozenset]:
    orders_dict = {o.order_id: o for o in orders}
    valid_clusterizations_archive: Set[frozenset] = set()
    population: List[Individual] = []

    # 1. Initialize random population (In production, use nearest-neighbor seeding)
    for _ in range(population_size):
        ind = Individual()
        trip_counter = 1
        # Group strictly by warehouse
        for wh_id in set(o.warehouse_id for o in orders):
            wh_orders = [o for o in orders if o.warehouse_id == wh_id]
            random.shuffle(wh_orders)

            # Chunk orders into initial trips
            chunk_size = constraints.max_order_count
            for i in range(0, len(wh_orders), chunk_size):
                chunk = wh_orders[i:i + chunk_size]
                trans_type = random.choices(
                    list(constraints.transport_distribution.keys()),
                    weights=list(constraints.transport_distribution.values())
                )[0]

                ind.trips[trip_counter] = Trip(
                    trip_id=trip_counter,
                    warehouse_id=wh_id,
                    transport_type=trans_type,
                    order_ids=[o.order_id for o in chunk]
                )
                trip_counter += 1

        evaluate_fitness(ind, orders_dict, constraints, warehouses_dict)
        population.append(ind)

    # 2. Main Evolutionary Loop
    for gen in range(generations):
        # Sort by fitness (lowest is best)
        population.sort(key=lambda x: x.fitness_score)

        # Archive valid solutions to fulfill the "thousands of combinations" requirement
        for ind in population:
            if ind.is_valid:
                valid_clusterizations_archive.add(ind.get_trip_sets())

        next_population = population[:10]  # Elitism: keep top 10 best

        while len(next_population) < population_size:
            # Tournament selection
            p1 = min(random.sample(population[:25], 2), key=lambda x: x.fitness_score)
            p2 = min(random.sample(population[:25], 2), key=lambda x: x.fitness_score)

            child = crossover(p1, p2)

            if random.random() < 0.3:  # 30% mutation rate
                child = mutate(child, orders)

            evaluate_fitness(child, orders_dict, constraints, warehouses_dict)
            next_population.append(child)

        population = next_population

        if gen % 100 == 0:
            print(
                f"Gen {gen} | Best Fitness: {population[0].fitness_score:.2f} | Valid Archieved: {len(valid_clusterizations_archive)}")

    return valid_clusterizations_archive