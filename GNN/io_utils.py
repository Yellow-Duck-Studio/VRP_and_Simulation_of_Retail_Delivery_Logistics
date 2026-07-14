"""
Загрузка исходных данных строго под присланную схему:

warehouses.csv:      task_id, warehouse_id, lat, lon
transport_types.csv: code, approx_speed_kmh, max_payload_kg,
                      fixed_fee, per_km_fee, per_order_fee, per_kg_min_fee
orders.csv:           task_id, order_id, warehouse_id, order_lat, order_lon,
                      pickup_ready_at, created_at, delivery_deadline_at, total_mass_kg

task_id/warehouse_id/order_id могут быть и числом, и строкой -> везде
приводим к str для единообразных ключей (в т.ч. при сверке с solutions.json,
где JSON-ключи всегда строки).

solutions.json (формат солвера, как в примере):
{
  "task_1": [
      [["1","2"]],   <- разбиение для warehouse_id=1 (первого по сортировке)
      [["3"]]        <- разбиение для warehouse_id=2
  ]
}
Порядок элементов списка = порядок warehouse_id по возрастанию (сортировка
как строк, если warehouse_id не приводится к int, иначе как чисел).
ВАЖНО: если твой солвер пишет warehouse_id явно (например, дампит словарь
{"1": [...], "2": [...]}), это тоже поддерживается — см. _match_solution.

С тех пор как brute_force_ilp.py стал учитывать ограниченный штат курьеров
(concurrency-constraint в ILP), каждый склад в solutions.json может
опционально нести с собой то значение max_couriers, под которое его
разбиение оптимизировано:
{
  "task_1": {
      "1": {"clusters": [["1","2"]], "max_couriers": 3},
      "2": {"clusters": [["3"]],     "max_couriers": 3}
  }
}
Старый формат (голый список кластеров на склад, без max_couriers) по-прежнему
поддерживается — тогда WarehouseInstance.max_couriers остаётся None, и
дальше по пайплайну используется дефолт (см. GNN/config.py::DEFAULT_MAX_COURIERS).
_match_solution понимает оба варианта.
"""

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd


@dataclass
class TransportTariff:
    code: str
    approx_speed_kmh: float
    max_payload_kg: float
    fixed_fee: float = 0.0
    per_km_fee: float = 0.0
    per_order_fee: float = 0.0
    per_kg_min_fee: float = 0.0


@dataclass
class WarehouseInstance:
    task_id: str
    warehouse_id: str
    warehouse_lat: float
    warehouse_lon: float
    orders: List[dict]                   # см. _order_row_to_dict
    clusters: Optional[List[List[str]]]  # ground-truth разбиение (order_id как str)
    max_couriers: Optional[int] = None   # штат, под который optimized clusters (None = неизвестен/старый формат)


def load_transport_types(path: str) -> List[TransportTariff]:
    return load_transport_types_with_optional_couriers(path, couriers_csv=None)


def _aggregate_courier_fees(couriers_csv: str) -> dict[str, dict[str, float]]:
    couriers_df = pd.read_csv(couriers_csv)
    fee_columns = {"per_km_fee", "per_order_fee"}
    if not fee_columns.issubset(couriers_df.columns):
        return {}

    transport_column = "transport_type_normalized" if "transport_type_normalized" in couriers_df.columns else "transport_type"
    alias_map = {
        "moped": "bike",
        "walking": "foot",
    }

    grouped = (
        couriers_df.groupby(transport_column, dropna=False)[["per_km_fee", "per_order_fee"]]
        .mean()
        .reset_index()
    )

    result: dict[str, dict[str, float]] = {}
    for row in grouped.itertuples():
        transport_key = alias_map.get(str(getattr(row, transport_column)), str(getattr(row, transport_column)))
        result[transport_key] = {
            "per_km_fee": float(row.per_km_fee),
            "per_order_fee": float(row.per_order_fee),
        }
    return result


def load_transport_types_with_optional_couriers(
    path: str,
    couriers_csv: Optional[str] = None,
) -> List[TransportTariff]:
    df = pd.read_csv(path)
    courier_fees = _aggregate_courier_fees(couriers_csv) if couriers_csv else {}
    return [
        TransportTariff(
            code=str(row.code),
            approx_speed_kmh=float(row.approx_speed_kmh),
            max_payload_kg=float(row.max_payload_kg),
            fixed_fee=float(getattr(row, "fixed_fee", 0.0)),
            per_km_fee=float(getattr(row, "per_km_fee", courier_fees.get(str(row.code), {}).get("per_km_fee", 0.0))),
            per_order_fee=float(getattr(row, "per_order_fee", courier_fees.get(str(row.code), {}).get("per_order_fee", 0.0))),
            per_kg_min_fee=float(getattr(row, "per_kg_min_fee", 0.0)),
        )
        for row in df.itertuples()
    ]


def _order_row_to_dict(row) -> dict:
    return {
        "order_id": str(row.order_id),
        "lat": float(row.order_lat),
        "lon": float(row.order_lon),
        "mass_kg": float(row.total_mass_kg),
        "pickup_ready_at": pd.Timestamp(row.pickup_ready_at),
        "created_at": pd.Timestamp(row.created_at),
        "delivery_deadline_at": pd.Timestamp(row.delivery_deadline_at),
    }


def _unwrap_warehouse_solution(raw):
    """
    A per-warehouse entry in solutions.json can be either:
      - the new format: {"clusters": [[...], ...], "max_couriers": M}
      - the old format: a bare list of clusters, e.g. [["1","2"], ["3"]]
    Returns (clusters, max_couriers), with max_couriers=None for the old
    format or if the key is simply absent.
    """
    if raw is None:
        return None, None
    if isinstance(raw, dict) and "clusters" in raw:
        return raw["clusters"], raw.get("max_couriers")
    return raw, None  # old format: raw IS the list of clusters


def _match_solution(sol_for_task, warehouse_ids_sorted: List[str], warehouse_id: str, w_idx: int):
    """Поддерживает и list-по-позиции, и dict, keyed by warehouse_id (оба
    формата per-warehouse значений — см. _unwrap_warehouse_solution)."""
    if sol_for_task is None:
        return None, None
    if isinstance(sol_for_task, dict):
        raw = sol_for_task.get(warehouse_id)
        if raw is None:
            raw = sol_for_task.get(str(warehouse_id))
        return _unwrap_warehouse_solution(raw)
    if isinstance(sol_for_task, list):
        if w_idx < len(sol_for_task):
            return _unwrap_warehouse_solution(sol_for_task[w_idx])
    return None, None


def load_instances(
    warehouses_csv: str,
    orders_csv: str,
    solutions_json: Optional[str] = None,
) -> List[WarehouseInstance]:
    wh_df = pd.read_csv(warehouses_csv, dtype={"task_id": str, "warehouse_id": str})
    orders_df = pd.read_csv(orders_csv, dtype={"task_id": str, "warehouse_id": str, "order_id": str})
    orders_by_key = {
        key: group
        for key, group in orders_df.groupby(["task_id", "warehouse_id"], sort=False)
    }

    solutions_raw = {}
    if solutions_json:
        with open(solutions_json) as f:
            solutions_raw = json.load(f)

    instances = []
    for task_id, wh_task_df in wh_df.groupby("task_id"):
        sol_for_task = solutions_raw.get(task_id) or solutions_raw.get(f"task_{task_id}")
        warehouse_ids_sorted = sorted(wh_task_df["warehouse_id"].tolist())

        for w_idx, warehouse_id in enumerate(warehouse_ids_sorted):
            wh_row = wh_task_df[wh_task_df["warehouse_id"] == warehouse_id].iloc[0]
            order_rows = orders_by_key.get((task_id, warehouse_id))
            if order_rows is None or order_rows.empty:
                continue
            orders = [_order_row_to_dict(r) for r in order_rows.itertuples()]

            clusters, max_couriers = _match_solution(sol_for_task, warehouse_ids_sorted, warehouse_id, w_idx)
            if clusters is not None:
                clusters = [[str(oid) for oid in cluster] for cluster in clusters]

            instances.append(
                WarehouseInstance(
                    task_id=task_id,
                    warehouse_id=warehouse_id,
                    warehouse_lat=float(wh_row["lat"]),
                    warehouse_lon=float(wh_row["lon"]),
                    orders=orders,
                    clusters=clusters,
                    max_couriers=max_couriers,
                )
            )
    return instances