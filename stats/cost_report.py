from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from itertools import permutations
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

import pandas as pd


MAX_CLUSTER_SIZE = 5
EARTH_R_KM = 6371.0088


@dataclass
class TransportTariff:
    code: str
    approx_speed_kmh: float
    max_payload_kg: float
    fixed_fee: float
    per_km_fee: float
    per_order_fee: float
    per_kg_min_fee: float


@dataclass
class DatasetContext:
    orders_by_task: dict[str, dict[str, dict[str, Any]]]
    warehouses_by_task: dict[str, dict[str, tuple[float, float]]]
    tariffs: list[TransportTariff]
    cluster_cost_cache: dict[tuple[str, str, tuple[str, ...]], float | None]


@dataclass
class SourceSummary:
    source: str
    total_cost: float | None
    feasible_units: int
    total_units: int
    notes: str = ""


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_R_KM * asin(sqrt(a))


def load_dataset_context(data_dir: Path) -> DatasetContext:
    orders_df = pd.read_csv(data_dir / "orders.csv", dtype={"task_id": str, "warehouse_id": str, "order_id": str})
    warehouses_df = pd.read_csv(data_dir / "warehouses.csv", dtype={"task_id": str, "warehouse_id": str})
    transport_df = pd.read_csv(data_dir / "transport_types.csv")

    orders_by_task: dict[str, dict[str, dict[str, Any]]] = {}
    for row in orders_df.itertuples():
        orders_by_task.setdefault(str(row.task_id), {})[str(row.order_id)] = {
            "order_id": str(row.order_id),
            "warehouse_id": str(row.warehouse_id),
            "lat": float(row.order_lat),
            "lon": float(row.order_lon),
            "mass_kg": float(row.total_mass_kg),
            "pickup_ready_at": pd.Timestamp(row.pickup_ready_at),
            "delivery_deadline_at": pd.Timestamp(row.delivery_deadline_at),
        }

    warehouses_by_task: dict[str, dict[str, tuple[float, float]]] = {}
    for row in warehouses_df.itertuples():
        warehouses_by_task.setdefault(str(row.task_id), {})[str(row.warehouse_id)] = (
            float(row.lat),
            float(row.lon),
        )

    tariffs = [
        TransportTariff(
            code=str(row.code),
            approx_speed_kmh=float(row.approx_speed_kmh),
            max_payload_kg=float(row.max_payload_kg),
            fixed_fee=float(getattr(row, "fixed_fee", 0.0)),
            per_km_fee=float(getattr(row, "per_km_fee", 0.0)),
            per_order_fee=float(getattr(row, "per_order_fee", 0.0)),
            per_kg_min_fee=float(getattr(row, "per_kg_min_fee", 0.0)),
        )
        for row in transport_df.itertuples()
    ]

    return DatasetContext(
        orders_by_task=orders_by_task,
        warehouses_by_task=warehouses_by_task,
        tariffs=tariffs,
        cluster_cost_cache={},
    )


def best_cluster_solution(
    warehouse_lat: float,
    warehouse_lon: float,
    orders: list[dict[str, Any]],
    tariffs: list[TransportTariff],
) -> dict[str, Any] | None:
    if not orders or len(orders) > MAX_CLUSTER_SIZE:
        return None

    total_mass = sum(order["mass_kg"] for order in orders)
    start_time = max(order["pickup_ready_at"] for order in orders)
    best: dict[str, Any] | None = None

    for tariff in tariffs:
        if total_mass > tariff.max_payload_kg:
            continue

        for perm in permutations(range(len(orders))):
            current_lat, current_lon = warehouse_lat, warehouse_lon
            current_time = start_time
            total_distance = 0.0
            feasible = True

            for index in perm:
                order = orders[index]
                distance = haversine_km(current_lat, current_lon, order["lat"], order["lon"])
                total_distance += distance
                travel_minutes = distance / tariff.approx_speed_kmh * 60.0
                current_time = current_time + pd.Timedelta(minutes=travel_minutes)
                if current_time > order["delivery_deadline_at"]:
                    feasible = False
                    break
                current_lat, current_lon = order["lat"], order["lon"]

            if not feasible:
                continue

            total_time_minutes = (current_time - start_time).total_seconds() / 60.0
            kg_min = total_mass * total_time_minutes
            cost = (
                tariff.fixed_fee
                + tariff.per_km_fee * total_distance
                + tariff.per_order_fee * len(orders)
                + tariff.per_kg_min_fee * kg_min
            )
            candidate = {
                "cost": cost,
                "transport": tariff.code,
            }
            if best is None or candidate["cost"] < best["cost"]:
                best = candidate

    return best


def evaluate_partition_cost(
    task_id: str,
    clusters: list[dict[str, Any]],
    context: DatasetContext,
) -> float | None:
    task_orders = context.orders_by_task.get(task_id, {})
    task_warehouses = context.warehouses_by_task.get(task_id, {})
    seen: set[str] = set()
    total_cost = 0.0

    for cluster in clusters:
        order_ids = [str(order_id) for order_id in cluster["order_ids"]]
        if not order_ids:
            return None
        if len(order_ids) > MAX_CLUSTER_SIZE:
            return None
        if any(order_id in seen for order_id in order_ids):
            return None

        cluster_orders = []
        warehouse_ids = set()
        for order_id in order_ids:
            order = task_orders.get(order_id)
            if order is None:
                return None
            cluster_orders.append(order)
            warehouse_ids.add(order["warehouse_id"])
            seen.add(order_id)

        if len(warehouse_ids) != 1:
            return None

        warehouse_id = cluster.get("warehouse_id")
        if warehouse_id is None:
            warehouse_id = next(iter(warehouse_ids))
        warehouse = task_warehouses.get(str(warehouse_id))
        if warehouse is None:
            return None

        cache_key = (task_id, str(warehouse_id), tuple(sorted(order_ids)))
        if cache_key not in context.cluster_cost_cache:
            solution = best_cluster_solution(
                warehouse_lat=warehouse[0],
                warehouse_lon=warehouse[1],
                orders=cluster_orders,
                tariffs=context.tariffs,
            )
            context.cluster_cost_cache[cache_key] = None if solution is None else float(solution["cost"])

        cached_cost = context.cluster_cost_cache[cache_key]
        if cached_cost is None:
            return None
        total_cost += cached_cost

    if seen != set(task_orders.keys()):
        return None

    return total_cost


def normalize_archive_clusterizations(raw_task_value: Any) -> list[list[dict[str, Any]]]:
    normalized: list[list[dict[str, Any]]] = []
    if not isinstance(raw_task_value, list):
        return normalized

    for entry in raw_task_value:
        if isinstance(entry, dict) and "clusters" in entry:
            normalized.append(
                [
                    {
                        "warehouse_id": cluster.get("warehouse_id"),
                        "order_ids": cluster.get("order_ids", []),
                    }
                    for cluster in entry.get("clusters", [])
                ]
            )
        elif isinstance(entry, list):
            normalized.append(
                [
                    {
                        "warehouse_id": None,
                        "order_ids": cluster,
                    }
                    for cluster in entry
                ]
            )
    return normalized


def summarize_archive(source_name: str, archive_path: Path, context: DatasetContext) -> SourceSummary:
    with archive_path.open(encoding="utf-8") as file:
        archive = json.load(file)

    total_cost = 0.0
    feasible_units = 0
    total_units = 0
    invalid_tasks: list[str] = []

    for task_key, task_value in archive.items():
        task_id = str(task_key).replace("task_", "")
        clusterizations = normalize_archive_clusterizations(task_value)
        total_units += 1

        best_cost = None
        for clusters in clusterizations:
            candidate_cost = evaluate_partition_cost(task_id, clusters, context)
            if candidate_cost is None:
                continue
            if best_cost is None or candidate_cost < best_cost:
                best_cost = candidate_cost

        if best_cost is None:
            invalid_tasks.append(task_id)
            continue

        feasible_units += 1
        total_cost += best_cost

    notes = ""
    if invalid_tasks:
        notes = "invalid tasks: " + ", ".join(invalid_tasks[:10])
        if len(invalid_tasks) > 10:
            notes += ", ..."

    return SourceSummary(
        source=source_name,
        total_cost=round(total_cost, 4) if feasible_units else None,
        feasible_units=feasible_units,
        total_units=total_units,
        notes=notes,
    )


def summarize_gnn_predictions(source_name: str, predictions_path: Path) -> SourceSummary:
    with predictions_path.open(encoding="utf-8") as file:
        predictions = json.load(file)

    feasible = [row for row in predictions if row.get("feasible") and row.get("total_cost") is not None]
    total_cost = sum(float(row["total_cost"]) for row in feasible)
    return SourceSummary(
        source=source_name,
        total_cost=round(total_cost, 4) if feasible else None,
        feasible_units=len(feasible),
        total_units=len(predictions),
        notes="units = warehouses",
    )


def summarize_run_directory(run_dir: Path, context: DatasetContext) -> list[SourceSummary]:
    summaries: list[SourceSummary] = []
    for algorithm_dir in sorted(path for path in run_dir.iterdir() if path.is_dir()):
        archive_path = algorithm_dir / "master_clusterizations.json"
        if archive_path.exists():
            summaries.append(summarize_archive(algorithm_dir.name, archive_path, context))
    return summaries


def render_markdown(dataset_label: str, summaries: list[SourceSummary]) -> str:
    lines = [
        f"# Cost report: {dataset_label}",
        "",
        "| source | total_cost | feasible_units | total_units | notes |",
        "|---|---:|---:|---:|---|",
    ]
    for summary in summaries:
        total_cost = "-" if summary.total_cost is None else f"{summary.total_cost:.4f}"
        lines.append(
            f"| {summary.source} | {total_cost} | {summary.feasible_units} | {summary.total_units} | {summary.notes} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a unified cost comparison report for one dataset.")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--dataset-label", required=True)
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--gnn-predictions", default=None)
    parser.add_argument("--bruteforce-archive", default=None)
    parser.add_argument("--out-md", required=True)
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args()

    context = load_dataset_context(Path(args.data_dir))
    summaries: list[SourceSummary] = []

    if args.bruteforce_archive:
        summaries.append(
            summarize_archive("bruteforce", Path(args.bruteforce_archive), context)
        )
    if args.gnn_predictions:
        summaries.append(
            summarize_gnn_predictions("gnn", Path(args.gnn_predictions))
        )
    if args.run_dir:
        summaries.extend(summarize_run_directory(Path(args.run_dir), context))

    out_md = Path(args.out_md)
    out_json = Path(args.out_json)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)

    out_md.write_text(render_markdown(args.dataset_label, summaries), encoding="utf-8")
    out_json.write_text(
        json.dumps([asdict(summary) for summary in summaries], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved markdown report to {out_md}")
    print(f"Saved json report to {out_json}")


if __name__ == "__main__":
    main()
