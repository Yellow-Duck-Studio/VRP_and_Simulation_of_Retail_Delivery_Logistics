from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from evolutionary_algorithm.domain import Individual

CSV_FIELDNAMES = [
    "task_id",
    "warehouse_id",
    "clusterization_id",
    "cluster_id",
    "order_id",
    "transport_type",
]


def _normalize_task_id(task_key: str) -> str:
    if task_key.startswith("task_"):
        return task_key.removeprefix("task_")
    return task_key


def _active_trips(individual: Individual) -> list:
    return sorted(
        (trip for trip in individual.trips.values() if trip.order_ids),
        key=lambda trip: trip.trip_id,
    )


def individual_to_json_clusterization(individual: Individual) -> list[list[int]]:
    return [sorted(trip.order_ids) for trip in _active_trips(individual)]


def individual_to_csv_rows(
    task_id: str,
    clusterization_id: int,
    individual: Individual,
) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for trip in _active_trips(individual):
        for order_id in trip.order_ids:
            rows.append(
                {
                    "task_id": task_id,
                    "warehouse_id": trip.warehouse_id,
                    "clusterization_id": clusterization_id,
                    "cluster_id": trip.trip_id,
                    "order_id": order_id,
                    "transport_type": trip.transport_type,
                }
            )
    return rows


def build_json_archive(task_clusterizations: dict[str, list[Individual]]) -> dict[str, list[list[list[int]]]]:
    return {
        task_key: [individual_to_json_clusterization(individual) for individual in individuals]
        for task_key, individuals in task_clusterizations.items()
    }


def build_csv_rows(task_clusterizations: dict[str, list[Individual]]) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for task_key, individuals in task_clusterizations.items():
        task_id = _normalize_task_id(task_key)
        for clusterization_id, individual in enumerate(individuals, start=1):
            rows.extend(individual_to_csv_rows(task_id, clusterization_id, individual))
    return rows


def write_json_archive(task_clusterizations: dict[str, list[Individual]], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(build_json_archive(task_clusterizations), file, indent=4)
    return output_path


def write_csv_archive(task_clusterizations: dict[str, list[Individual]], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(build_csv_rows(task_clusterizations))
    return output_path


def save_clusterizations(
    task_clusterizations: dict[str, Iterable[Individual]],
    json_path: str | Path,
    *,
    csv_path: str | Path | None = None,
    save_json: bool = True,
    save_csv: bool = True,
) -> tuple[Path | None, Path | None]:
    normalized: dict[str, list[Individual]] = {
        task_key: list(individuals) for task_key, individuals in task_clusterizations.items()
    }
    json_output_path = Path(json_path)
    csv_output_path = Path(csv_path) if csv_path is not None else json_output_path.with_suffix(".csv")

    saved_json: Path | None = None
    saved_csv: Path | None = None

    if save_json:
        saved_json = write_json_archive(normalized, json_output_path)
    if save_csv:
        saved_csv = write_csv_archive(normalized, csv_output_path)

    return saved_json, saved_csv
