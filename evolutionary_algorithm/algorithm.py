from typing import List, Dict, Tuple, Set

from evolutionary_algorithm.domain import Individual, Trip, Order, Constraint
import random

from evolutionary_algorithm.evaluation import evaluate_fitness


def _copy_individual(individual: Individual) -> Individual:
    return Individual(trips={
        k: Trip(
            trip_id=v.trip_id,
            warehouse_id=v.warehouse_id,
            transport_type=v.transport_type,
            order_ids=list(v.order_ids),
        )
        for k, v in individual.trips.items()
    })


def _active_trips(individual: Individual) -> List[Trip]:
    return [t for t in individual.trips.values() if t.order_ids]


def _next_trip_id(trips: Dict[int, Trip]) -> int:
    return max(trips.keys()) + 1 if trips else 1


def _random_partition(items: List[int], k: int) -> List[List[int]]:
    """Split items into k non-empty groups."""
    shuffled = list(items)
    random.shuffle(shuffled)
    groups: List[List[int]] = [[shuffled[i]] for i in range(k)]
    for item in shuffled[k:]:
        groups[random.randint(0, k - 1)].append(item)
    return groups


def _mutate_swap(ind: Individual) -> None:
    """Move one order to another trip within the same warehouse."""
    active_trips = _active_trips(ind)
    if len(active_trips) < 2:
        return

    source_trip = random.choice(active_trips)
    order_id_to_move = random.choice(source_trip.order_ids)

    target_trips = [
        t for t in active_trips
        if t.warehouse_id == source_trip.warehouse_id and t.trip_id != source_trip.trip_id
    ]
    if not target_trips:
        return

    target_trip = random.choice(target_trips)
    source_trip.order_ids.remove(order_id_to_move)
    target_trip.order_ids.append(order_id_to_move)


def _mutate_detach(ind: Individual) -> None:
    """Detach one order from a cluster into a new single-order cluster."""
    splittable = [t for t in _active_trips(ind) if len(t.order_ids) >= 2]
    if not splittable:
        return

    source_trip = random.choice(splittable)
    order_id = random.choice(source_trip.order_ids)
    source_trip.order_ids.remove(order_id)

    new_trip_id = _next_trip_id(ind.trips)
    ind.trips[new_trip_id] = Trip(
        trip_id=new_trip_id,
        warehouse_id=source_trip.warehouse_id,
        transport_type=source_trip.transport_type,
        order_ids=[order_id],
    )


def _mutate_merge(ind: Individual) -> None:
    """Merge two clusters from the same warehouse into one."""
    by_warehouse: Dict[int, List[Trip]] = {}
    for trip in _active_trips(ind):
        by_warehouse.setdefault(trip.warehouse_id, []).append(trip)

    mergeable = [wh for wh, trips in by_warehouse.items() if len(trips) >= 2]
    if not mergeable:
        return

    warehouse_id = random.choice(mergeable)
    trip_a, trip_b = random.sample(by_warehouse[warehouse_id], 2)

    trip_a.order_ids.extend(trip_b.order_ids)
    trip_b.order_ids.clear()


def _mutate_split(ind: Individual) -> None:
    """Split one cluster into a random number of smaller clusters."""
    splittable = [t for t in _active_trips(ind) if len(t.order_ids) >= 2]
    if not splittable:
        return

    source_trip = random.choice(splittable)
    orders = list(source_trip.order_ids)
    num_clusters = random.randint(2, len(orders))
    clusters = _random_partition(orders, num_clusters)

    source_trip.order_ids = clusters[0]
    for cluster_orders in clusters[1:]:
        new_trip_id = _next_trip_id(ind.trips)
        ind.trips[new_trip_id] = Trip(
            trip_id=new_trip_id,
            warehouse_id=source_trip.warehouse_id,
            transport_type=source_trip.transport_type,
            order_ids=cluster_orders,
        )


def mutate(individual: Individual, all_orders: List[Order]) -> Individual:
    """Apply one random mutation: swap, detach, merge, or split."""
    new_ind = _copy_individual(individual)
    random.choice([
        _mutate_swap,
        _mutate_detach,
        _mutate_merge,
        _mutate_split,
    ])(new_ind)
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

            if random.random() < 0.5:  # 50% mutation rate
                child = mutate(child, orders)

            evaluate_fitness(child, orders_dict, constraints, warehouses_dict)
            next_population.append(child)

        population = next_population

        if gen % 100 == 0:
            print(
                f"Gen {gen} | Best Fitness: {population[0].fitness_score:.2f} | Valid Archieved: {len(valid_clusterizations_archive)}")

    return valid_clusterizations_archive