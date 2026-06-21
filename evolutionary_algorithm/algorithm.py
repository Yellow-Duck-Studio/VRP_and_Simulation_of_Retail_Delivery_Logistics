from typing import List, Dict, Tuple, Set

from evolutionary_algorithm.domain import Individual, Trip, Order, Constraint
import random

from evolutionary_algorithm.evaluation import evaluate_fitness

# Algorithms
from evolutionary_algorithm.domain import Algorithms
from dbscan import seed_population
from heuristics.savings_core import build_clarke_wright_solution
from heuristics.destroy_repair_core import run_destroy_repair
from sweep_seeding import seed_population as seed_population_sweep

from evolutionary_algorithm.evaluation import haversine_distance, evaluate_cluster_direction

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

def _mutate_destroy_repair(
        ind: Individual,
        orders_dict: Dict[int, Order],
        warehouses: Dict[int, Tuple[float, float]],
        constraints: Constraint
) -> None:
    """Removes the 'weakest' orders from clusters and greedily re-inserts them."""
    active_trips = [t for t in _active_trips(ind) if len(t.order_ids) > 1]
    if not active_trips:
        return

    orphaned_orders: List[Tuple[int, int]] = []  # (order_id, warehouse_id)

    # --- 1. DESTROY PHASE (Worst Removal) ---
    # Pick a few random trips to ruin (e.g., 1 to 3 trips)
    num_to_destroy = random.randint(1, min(3, len(active_trips)))
    target_trips = random.sample(active_trips, num_to_destroy)

    for trip in target_trips:
        wh_lat, wh_lon = warehouses[trip.warehouse_id]
        worst_order_id = None
        max_dist = -1.0

        # Define "weakest" as the order furthest from the warehouse
        # (Alternatively, you could evaluate directional penalty drop)
        for oid in trip.order_ids:
            order = orders_dict[oid]
            dist = haversine_distance(wh_lat, wh_lon, order.lat, order.lon)
            if dist > max_dist:
                max_dist = dist
                worst_order_id = oid

        if worst_order_id:
            trip.order_ids.remove(worst_order_id)
            orphaned_orders.append((worst_order_id, trip.warehouse_id))

    # --- 2. REPAIR PHASE (Greedy Insertion) ---
    for order_id, wh_id in orphaned_orders:
        order = orders_dict[order_id]
        best_trip = None
        best_cost_increase = float('inf')

        # Find all active trips for this warehouse
        candidate_trips = [t for t in _active_trips(ind) if t.warehouse_id == wh_id]

        for trip in candidate_trips:
            # Hard Constraint 1: Order count
            if len(trip.order_ids) >= constraints.max_order_count:
                continue

            # Hard Constraint 2: Weight capacity
            current_weight = sum(orders_dict[oid].total_mass_kg for oid in trip.order_ids)
            if current_weight + order.total_mass_kg > constraints.max_weight_per_transport[trip.transport_type]:
                continue

            # Heuristic Cost: How much does inserting this ruin the directional cohesion?
            trip_orders = [orders_dict[oid] for oid in trip.order_ids] + [order]
            wh_lat, wh_lon = warehouses[wh_id]

            cost = evaluate_cluster_direction(wh_lat, wh_lon, trip_orders)

            if cost < best_cost_increase:
                best_cost_increase = cost
                best_trip = trip

        # Resolve: Insert into the best found trip, or create a new one
        if best_trip:
            best_trip.order_ids.append(order_id)
        else:
            new_trip_id = _next_trip_id(ind.trips)
            # Pick a valid transport type based on your distribution
            trans_type = random.choices(
                list(constraints.transport_distribution.keys()),
                weights=list(constraints.transport_distribution.values())
            )[0]

            ind.trips[new_trip_id] = Trip(
                trip_id=new_trip_id,
                warehouse_id=wh_id,
                transport_type=trans_type,
                order_ids=[order_id]
            )


def mutate(
        individual: Individual,
        orders_dict: Dict[int, Order],
        warehouses_dict: Dict[int, Tuple[float, float]],
        constraints: Constraint
) -> Individual:
    """Apply one random mutation."""
    new_ind = _copy_individual(individual)

    # Give the intelligent LNS operator a good chance of being selected
    mutation_type = random.choices(
        ['swap', 'detach', 'merge', 'split', 'destroy_repair'],
        weights=[0.2, 0.15, 0.15, 0.1, 0.4]  # 40% chance for Destroy & Repair
    )[0]

    if mutation_type == 'swap':
        _mutate_swap(new_ind)
    elif mutation_type == 'detach':
        _mutate_detach(new_ind)
    elif mutation_type == 'merge':
        _mutate_merge(new_ind)
    elif mutation_type == 'split':
        _mutate_split(new_ind)
    elif mutation_type == 'destroy_repair':
        _mutate_destroy_repair(new_ind, orders_dict, warehouses_dict, constraints)

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

def init_random_population(orders, constraints, population_size) -> List[Individual]:
    population: List[Individual] = []
    for _ in range(population_size):
        ind = Individual()
        trip_counter = 1
        for wh_id in set(o.warehouse_id for o in orders):
            wh_orders = [o for o in orders if o.warehouse_id == wh_id]
            random.shuffle(wh_orders)
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
        population.append(ind)
    return population

def run_evolutionary_clustering(
        algorithm: Algorithms,
        orders: List[Order],
        warehouses_dict: Dict[int, Tuple[float, float]],  # warehouse_id -> (lat, lon)
        constraints: Constraint,
        generations: int = 1000,
        population_size: int = 50
) -> Set[frozenset]:
    orders_dict = {o.order_id: o for o in orders}
    valid_clusterizations_archive: Set[frozenset] = set()
    # 1. Initializing population based on chosen algorithm

    if algorithm == Algorithms.DBSCAN:
        population = seed_population(orders, warehouses_dict, constraints, population_size=population_size)

    elif algorithm == Algorithms.RND:
        population = init_random_population(orders, constraints, population_size)

    elif algorithm == Algorithms.SWEEP:
        population = seed_population_sweep(orders, warehouses_dict, constraints, population_size=population_size)

    elif algorithm == Algorithms.CLWR:
        base = build_clarke_wright_solution(orders, warehouses_dict, constraints)
        population = [base] + [mutate(base, orders) for _ in range(population_size - 1)]

    elif algorithm == Algorithms.DSTR:
        seed_individual = init_random_population(orders, constraints, population_size=1)[0]
        population = run_destroy_repair(
            seed_individual=seed_individual,
            orders=orders,
            warehouses_dict=warehouses_dict,
            constraints=constraints,
            iterations=200,
            destroy_fraction=0.2,
            max_solutions=population_size,
            rng_seed=42,
        )
        if len(population) < population_size:
            population += init_random_population(orders, constraints, population_size - len(population))

    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")

    for ind in population:
        evaluate_fitness(ind, orders_dict, constraints, warehouses_dict)

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
                child = mutate(child, orders_dict, warehouses_dict, constraints)

            evaluate_fitness(child, orders_dict, constraints, warehouses_dict)
            next_population.append(child)

        population = next_population

        if gen % 100 == 0:
            print(
                f"Gen {gen} | Best Fitness: {population[0].fitness_score:.2f} | Valid Archieved: {len(valid_clusterizations_archive)}")

    return valid_clusterizations_archive