"""
cost = fixed_fee + per_km_fee * route_distance_km
                  + per_order_fee * order_count
                  + per_kg_min_fee * route_kg_min

route_kg_min = sum over legs of (leg_duration_min * remaining_mass_kg),
where remaining_mass_kg is the mass of all orders NOT YET delivered at the
start of that leg. It starts at total_mass_kg and decreases after each
delivery -- the courier only pays kg*min for the cargo it is still
carrying, not the full cluster mass for the whole route (confirmed against
the checker's route_stats()).

Проверка допустимости кластера для тарифа:
  - все заказы одного типа транспорта (это гарантируется тем, что мы
    перебираем весь кластер целиком под один тариф)
  - суммарная масса кластера <= max_payload_kg
  - <= MAX_CLUSTER_SIZE заказов
  - маршрут успевает довезти КАЖДЫЙ заказ до его delivery_deadline_at,
    при этом старт маршрута = max(pickup_ready_at по заказам кластера)
    (см. допущение в module docstring io_utils.py) -- курьер не может
    выехать, пока не готовы все заказы кластера.
"""

import heapq
import itertools
from typing import Dict, List, Optional

import pandas as pd

from config import MAX_CLUSTER_SIZE
from geo import haversine_km
from io_utils import TransportTariff


def best_route_for_transport(
        warehouse_lat: float,
        warehouse_lon: float,
        orders: List[dict],
        tariff: TransportTariff,
) -> Optional[dict]:
    n = len(orders)
    if n == 0 or n > MAX_CLUSTER_SIZE:
        return None

    total_mass = sum(o["mass_kg"] for o in orders)
    if total_mass > tariff.max_payload_kg:
        return None

    start_time = max(o["pickup_ready_at"] for o in orders)

    best = None
    for perm in itertools.permutations(range(n)):
        cur_lat, cur_lon = warehouse_lat, warehouse_lon
        cur_time = start_time
        total_dist = 0.0
        kg_min = 0.0
        # Масса, которую курьер ещё везёт (не выгруженную к началу текущего
        # участка). Убывает после каждой доставки -- курьер платит по
        # кг*мин только за груз, который всё ещё у него на руках.
        remaining_mass = total_mass
        feasible = True
        for idx in perm:
            o = orders[idx]
            d = haversine_km(cur_lat, cur_lon, o["lat"], o["lon"])
            total_dist += d
            travel_min = d / tariff.approx_speed_kmh * 60.0
            # На этом участке курьер везёт remaining_mass (ещё недоставленный груз).
            kg_min += travel_min * remaining_mass
            cur_time = cur_time + pd.Timedelta(minutes=travel_min)
            if cur_time > o["delivery_deadline_at"]:
                feasible = False
                break
            cur_lat, cur_lon = o["lat"], o["lon"]
            remaining_mass -= o["mass_kg"]
        if not feasible:
            continue

        # Обратное плечо: последняя точка доставки -> склад. Курьер физически
        # обязан вернуться, машина едет пустой (в kg_min ничего не добавляем,
        # remaining_mass к этому моменту == 0), но расстояние и время реальны.
        return_dist = haversine_km(cur_lat, cur_lon, warehouse_lat, warehouse_lon)
        total_dist += return_dist
        return_min = return_dist / tariff.approx_speed_kmh * 60.0
        finish_time = cur_time + pd.Timedelta(minutes=return_min)

        total_time_min = (finish_time - start_time).total_seconds() / 60.0

        cost = (
                tariff.fixed_fee
                + tariff.per_km_fee * total_dist          # уже включает return_dist
                + tariff.per_order_fee * n
                + tariff.per_kg_min_fee * kg_min           # без изменений — на обратном плече remaining_mass=0
        )
        if best is None or cost < best["cost"]:
            best = {
                "cost": cost,
                "distance_km": total_dist,
                "duration_min": total_time_min,
                "start_at": start_time,        # момент выезда со склада
                "finish_at": finish_time,       # момент возврата на склад (курьер снова свободен)
                "order_sequence": [orders[i]["order_id"] for i in perm],
                "transport": tariff.code,
            }
    return best


def best_cluster_solution(
        warehouse_lat: float,
        warehouse_lon: float,
        orders: List[dict],
        tariffs: List[TransportTariff],
) -> Optional[dict]:
    best = None
    for tariff in tariffs:
        res = best_route_for_transport(warehouse_lat, warehouse_lon, orders, tariff)
        if res is not None and (best is None or res["cost"] < best["cost"]):
            best = res
    return best


def clustering_total_cost(
        warehouse_lat: float,
        warehouse_lon: float,
        orders_by_id: Dict[str, dict],
        clusters: List[List[str]],
        tariffs: List[TransportTariff],
) -> Optional[float]:
    total = 0.0
    seen = set()
    for cluster_ids in clusters:
        if len(cluster_ids) > MAX_CLUSTER_SIZE:
            return None
        for oid in cluster_ids:
            if oid in seen:
                return None
            seen.add(oid)
        cluster_orders = [orders_by_id[oid] for oid in cluster_ids]
        sol = best_cluster_solution(warehouse_lat, warehouse_lon, cluster_orders, tariffs)
        if sol is None:
            return None
        total += sol["cost"]
    if seen != set(orders_by_id.keys()):
        return None
    return total


def required_couriers(cluster_solutions: List[dict]) -> int:
    """
    Минимальное число курьеров, необходимое чтобы выполнить набор рейсов
    (каждый — dict с ключами start_at/finish_at из best_cluster_solution),
    с учётом того, что один курьер может взять следующий рейс, если он
    освобождается не позже, чем начинается следующий. Классический sweep
    line с min-heap по времени освобождения.

    Используется в decode.py::enforce_courier_capacity и может
    использоваться в infer.py для диагностики (сколько курьеров реально
    требует предсказание модели).
    """
    ordered = sorted(cluster_solutions, key=lambda s: s["start_at"])
    heap = []
    for s in ordered:
        if heap and heap[0] <= s["start_at"]:
            heapq.heapreplace(heap, s["finish_at"])
        else:
            heapq.heappush(heap, s["finish_at"])
    return len(heap)
