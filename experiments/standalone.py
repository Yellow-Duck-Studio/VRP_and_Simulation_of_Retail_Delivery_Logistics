from __future__ import annotations

from typing import Dict, List, Tuple

from dbscan import seed_population
from evolutionary_algorithm.algorithm import _copy_individual, init_random_population
from evolutionary_algorithm.domain import Constraint, Individual, Order
from evolutionary_algorithm.evaluation import evaluate_fitness
from evolutionary_algorithm.fitness_registry import FitnessConfig
from heuristics.destroy_repair_core import run_destroy_repair
from heuristics.savings_core import build_clarke_wright_solution
from sweep_seeding import seed_population as seed_population_sweep


def _sorted_unique(individuals: List[Individual]) -> List[Individual]:
    unique: Dict[frozenset, Individual] = {}
    for individual in individuals:
        signature = individual.get_trip_sets()
        if signature not in unique:
            unique[signature] = _copy_individual(individual)

    values = sorted(unique.values(), key=lambda item: item.fitness_score)
    valid_values = [item for item in values if item.is_valid]
    return valid_values if valid_values else values


def run_standalone_algorithm(
    algorithm_name: str,
    orders: List[Order],
    warehouses_dict: Dict[int, Tuple[float, float]],
    constraints: Constraint,
    population_size: int,
    fitness_config: FitnessConfig,
) -> List[Individual]:
    orders_dict = {order.order_id: order for order in orders}

    if algorithm_name == "dbscan":
        individuals = seed_population(orders, warehouses_dict, constraints, population_size=population_size)
    elif algorithm_name == "sweep":
        individuals = seed_population_sweep(orders, warehouses_dict, constraints, population_size=population_size)
    elif algorithm_name == "random":
        individuals = init_random_population(orders, constraints, population_size)
    elif algorithm_name == "clarke_wright":
        individuals = [build_clarke_wright_solution(orders, warehouses_dict, constraints)]
    elif algorithm_name == "destroy_repair":
        seed_individual = init_random_population(orders, constraints, population_size=1)[0]
        individuals = run_destroy_repair(
            seed_individual=seed_individual,
            orders=orders,
            warehouses_dict=warehouses_dict,
            constraints=constraints,
            iterations=200,
            destroy_fraction=0.2,
            max_solutions=population_size,
            rng_seed=42,
        )
    else:
        raise ValueError(f"Unsupported standalone algorithm: {algorithm_name}")

    for individual in individuals:
        evaluate_fitness(individual, orders_dict, constraints, warehouses_dict, fitness_config)

    return _sorted_unique(individuals)
