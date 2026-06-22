"""
sweep_seeding.py

Drop-in replacement for the random init block in run_evolutionary_clustering().
Matches the exact contract and architecture of dbscan_seeding.py.

Usage:
    from sweep_seeding import seed_population

    # Inside run_evolutionary_clustering():
    elif algorithm == Algorithms.SWEEP:
        population = seed_population(orders, warehouses_dict, constraints, population_size=population_size)
"""

import math
import random
from typing import Dict, List, Set, Tuple

import numpy as np

from evolutionary_algorithm.domain import Constraint, Individual, Order, Trip


def _build_individual_sweep(
        orders: List[Order],
        warehouses_dict: Dict[int, Tuple[float, float]],
        constraints: Constraint,
        transport_type: str,
        start_angle: float,
        clockwise: bool,
        trip_counter_start: int = 1,
) -> Individual:
    """
    Строит одну особь (Individual), нарезая заказы вокруг каждого склада
    методом радиального заметания (Sweep) под определенным углом.
    """
    ind = Individual()
    trip_counter = trip_counter_start

    # Группируем заказы по складам
    by_wh: Dict[int, List[Order]] = {}
    for o in orders:
        by_wh.setdefault(o.warehouse_id, []).append(o)

    max_weight = constraints.max_weight_per_transport[transport_type]
    max_count = constraints.max_order_count

    for wh_id, wh_orders in by_wh.items():
        if wh_id not in warehouses_dict:
            continue

        wh_lat, wh_lon = warehouses_dict[wh_id]
        lat_rad = math.radians(wh_lat)

        # Шаг 1: Вычисляем полярный угол каждого заказа (с поправкой на кривизну из evaluation.py)
        order_angles: List[Tuple[float, Order]] = []
        for o in wh_orders:
            dy = o.lat - wh_lat
            dx = (o.lon - wh_lon) * math.cos(lat_rad)

            angle = math.atan2(dy, dx)
            if angle < 0:
                angle += 2 * math.pi

            # Сдвигаем угол относительно стартовой позиции луча
            shifted_angle = (angle - start_angle) % (2 * math.pi)
            if clockwise:
                shifted_angle = (2 * math.pi - shifted_angle) % (2 * math.pi)

            order_angles.append((shifted_angle, o))

        # Шаг 2: Сортируем заказы по ходу движения луча сканера
        order_angles.sort(key=lambda x: x[0])
        sorted_orders = [item[1] for item in order_angles]

        # Шаг 3: Нарезаем сектор на валидные рейсы курьера без превышения лимитов
        current_trip_orders: List[int] = []
        current_weight = 0.0

        for order in sorted_orders:
            would_exceed_count = len(current_trip_orders) + 1 > max_count
            would_exceed_weight = current_weight + order.total_mass_kg > max_weight

            if would_exceed_count or would_exceed_weight:
                # Закрываем текущую поездку, если она не пустая
                if current_trip_orders:
                    ind.trips[trip_counter] = Trip(
                        trip_id=trip_counter,
                        warehouse_id=wh_id,
                        transport_type=transport_type,
                        order_ids=current_trip_orders,
                    )
                    trip_counter += 1
                # Открываем новую поездку
                current_trip_orders = [order.order_id]
                current_weight = order.total_mass_kg
            else:
                current_trip_orders.append(order.order_id)
                current_weight += order.total_mass_kg

        # Сохраняем последний оставшийся рейс склада
        if current_trip_orders:
            ind.trips[trip_counter] = Trip(
                trip_id=trip_counter,
                warehouse_id=wh_id,
                transport_type=transport_type,
                order_ids=current_trip_orders,
            )
            trip_counter += 1

    return ind


def seed_population(
        orders: List[Order],
        warehouses_dict: Dict[int, Tuple[float, float]],
        constraints: Constraint,
        population_size: int = 50,
        seed: int = 0,
) -> List[Individual]:
    """
    Генерирует заданное количество (population_size) уникальных особей Sweep-методом.
    Полный аналог seed_population из dbscan_seeding.py.
    """
    rng = np.random.default_rng(seed)
    candidates: List[Individual] = []
    seen_sigs: Set[frozenset] = set()

    transport_types = list(constraints.transport_distribution.keys())

    # Генерируем плотную сетку углов: 72 шага по 5 градусов для максимального разнообразия
    num_angles = 72
    angles = [i * (2 * math.pi / num_angles) for i in range(num_angles)]
    directions = [False, True]  # False = против часовой, True = по часовой стрелке

    # Заполняем пул кандидатов комбинациями параметров
    for transport_type in transport_types:
        for start_angle in angles:
            for clockwise in directions:
                ind = _build_individual_sweep(
                    orders, warehouses_dict, constraints,
                    transport_type=transport_type,
                    start_angle=start_angle,
                    clockwise=clockwise
                )
                sig = ind.get_trip_sets()
                if sig not in seen_sigs:
                    seen_sigs.add(sig)
                    candidates.append(ind)

    # Если уникальных вариантов Sweep больше, чем размер популяции, сэмплируем случайные случайным образом
    if len(candidates) >= population_size:
        chosen = list(rng.choice(len(candidates), size=population_size, replace=False))
        return [candidates[i] for i in chosen]

    # Если уникальных Sweep-комбинаций не хватило, добиваем популяцию случайным разбиением (как в DBSCAN)
    population = list(candidates)
    while len(population) < population_size:
        ind = Individual()
        trip_counter = 1
        for wh_id in set(o.warehouse_id for o in orders):
            wh_orders = [o for o in orders if o.warehouse_id == wh_id]
            random.shuffle(wh_orders)
            chunk_size = constraints.max_order_count
            for i in range(0, len(wh_orders), chunk_size):
                chunk = wh_orders[i:i + chunk_size]
                t_type = random.choices(
                    list(constraints.transport_distribution.keys()),
                    weights=list(constraints.transport_distribution.values()),
                )[0]
                ind.trips[trip_counter] = Trip(
                    trip_id=trip_counter,
                    warehouse_id=wh_id,
                    transport_type=t_type,
                    order_ids=[o.order_id for o in chunk],
                )
                trip_counter += 1

        sig = ind.get_trip_sets()
        if sig not in seen_sigs:
            seen_sigs.add(sig)
            population.append(ind)

    return population[:population_size]
