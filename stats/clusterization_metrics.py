"""
clusterization_metrics.py
Подсчёт стоимости маршрутов и вывод статистики по разбиениям.

Использование:
    from clusterization_metrics import print_archive_stats

    print_archive_stats(
        master_archive=master_archive,
        tasks_orders=tasks_orders,
        tasks_warehouses=tasks_warehouses,
        fee_table=fee_table,
    )
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


# ---------------------------------------------------------------------------
# Geo
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _route_distance_km(
    warehouse_lat: float,
    warehouse_lon: float,
    orders: List[Any],   # List[Order], порядок объезда как в trip.order_ids
) -> float:
    if not orders:
        return 0.0
    total = 0.0
    prev_lat, prev_lon = warehouse_lat, warehouse_lon
    for o in orders:
        total += _haversine_km(prev_lat, prev_lon, o.lat, o.lon)
        prev_lat, prev_lon = o.lat, o.lon
    total += _haversine_km(prev_lat, prev_lon, warehouse_lat, warehouse_lon)
    return total


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

@dataclass
class TripCost:
    trip_id: int
    transport_type: str
    order_count: int
    route_distance_km: float
    total_mass_kg: float
    total_cost: float


def compute_trip_cost(
    trip: Any,                                   # Trip
    orders_dict: Dict[int, Any],                 # {order_id: Order}
    warehouses: Dict[int, Tuple[float, float]],  # {warehouse_id: (lat, lon)}
    fee_table: Dict[str, Dict[str, float]],
) -> TripCost:
    """
    cost = fixed_fee
         + per_km_fee    * route_distance
         + per_order_fee * order_count
         + per_kg_min_fee * total_mass_kg
    """
    fees = fee_table[trip.transport_type]
    wh_lat, wh_lon = warehouses.get(trip.warehouse_id, (0.0, 0.0))

    trip_orders = [orders_dict[oid] for oid in trip.order_ids if oid in orders_dict]
    distance    = _route_distance_km(wh_lat, wh_lon, trip_orders)
    mass        = sum(o.total_mass_kg for o in trip_orders)
    count       = len(trip_orders)

    total = (
        fees["fixed_fee"]
        + fees["per_km_fee"]     * distance
        + fees["per_order_fee"]  * count
        + fees["per_kg_min_fee"] * mass
    )

    return TripCost(
        trip_id=trip.trip_id,
        transport_type=trip.transport_type,
        order_count=count,
        route_distance_km=round(distance, 4),
        total_mass_kg=round(mass, 4),
        total_cost=round(total, 4),
    )


def compute_individual_cost(
    individual: Any,
    orders_dict: Dict[int, Any],
    warehouses: Dict[int, Tuple[float, float]],
    fee_table: Dict[str, Dict[str, float]],
) -> Tuple[float, List[TripCost]]:
    """Возвращает (суммарная стоимость кластеризации, список TripCost по каждому трипу)."""
    trip_costs = [
        compute_trip_cost(trip, orders_dict, warehouses, fee_table)
        for trip in individual.trips.values()
        if trip.order_ids
    ]
    total = sum(tc.total_cost for tc in trip_costs)
    return round(total, 4), trip_costs


# ---------------------------------------------------------------------------
# Statistics & pretty print
# ---------------------------------------------------------------------------

def print_archive_stats(
    master_archive: Dict[str, List[Any]],
    tasks_orders: Dict[str, List[Any]],
    tasks_warehouses: Dict[str, Dict[int, Tuple[float, float]]],
    fee_table: Dict[str, Dict[str, float]],
) -> None:
    """
    Выводит статистику стоимости по каждой задаче и каждой кластеризации.

    Parameters
    ----------
    master_archive   : {f"task_{task_id}": List[Individual]}
    tasks_orders     : {task_id: List[Order]}
    tasks_warehouses : {task_id: {warehouse_id: (lat, lon)}}
    fee_table        : {transport_type: {fixed_fee, per_km_fee,
                                         per_order_fee, per_kg_min_fee}}
    """
    grand_costs: List[float] = []

    for task_key, individuals in master_archive.items():
        task_id    = task_key.replace("task_", "")
        orders_dict = {o.order_id: o for o in tasks_orders.get(task_id, [])}
        warehouses  = tasks_warehouses.get(task_id, {})

        costs: List[float] = []
        for ind in individuals:
            total, _ = compute_individual_cost(ind, orders_dict, warehouses, fee_table)
            costs.append(total)

        grand_costs.extend(costs)

        if not costs:
            print(f"\n[{task_key}] No valid clusterizations.")
            continue

        best  = min(costs)
        worst = max(costs)
        avg   = sum(costs) / len(costs)

        best_idx = costs.index(best) + 1
        best_ind = individuals[costs.index(best)]
        _, best_trips = compute_individual_cost(best_ind, orders_dict, warehouses, fee_table)

        print(f"\n{'=' * 50}")
        print(f"  TASK {task_id}  |  {len(individuals)} clusterizations")
        print(f"{'=' * 50}")
        print(f"  Best  cost : {best:.2f}  (clusterization #{best_idx})")
        print(f"  Worst cost : {worst:.2f}")
        print(f"  Avg   cost : {avg:.2f}")
        print(f"\n  Best clusterization breakdown (#{best_idx}):")
        print(f"  {'trip':>5}  {'type':>5}  {'orders':>6}  {'km':>8}  {'kg':>8}  {'cost':>10}")
        print(f"  {'-'*5}  {'-'*5}  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*10}")
        for tc in best_trips:
            print(
                f"  {tc.trip_id:>5}  {tc.transport_type:>5}  "
                f"{tc.order_count:>6}  {tc.route_distance_km:>8.2f}  "
                f"{tc.total_mass_kg:>8.2f}  {tc.total_cost:>10.2f}"
            )
        print(f"  {'':>5}  {'':>5}  {'':>6}  {'':>8}  {'TOTAL':>8}  {best:>10.2f}")

    if grand_costs:
        print(f"\n{'=' * 50}")
        print(f"  OVERALL  |  {len(grand_costs)} clusterizations across all tasks")
        print(f"  Grand avg cost : {sum(grand_costs) / len(grand_costs):.2f}")
        print(f"  Grand min cost : {min(grand_costs):.2f}")
        print(f"  Grand max cost : {max(grand_costs):.2f}")
        print(f"{'=' * 50}\n")
