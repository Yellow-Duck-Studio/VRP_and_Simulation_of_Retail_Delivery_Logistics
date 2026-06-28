"""
clusterization_logger.py
Сохранение финального разбиения в JSON и CSV.

CSV формат:
task_id,warehouse_id,clusterization_id,cluster_id,order_id,transport_type
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

CSV_FIELDS = [
    "task_id",
    "warehouse_id",
    "clusterization_id",
    "cluster_id",
    "order_id",
    "transport_type",
]


def _iter_csv_rows(master_archive: Dict[str, List[Any]]):
    """Генератор строк CSV из master_archive {task_key: List[Individual]}."""
    for task_key, individuals in master_archive.items():
        task_id = task_key.replace("task_", "")
        for clust_idx, individual in enumerate(individuals, start=1):
            for trip in individual.trips.values():
                if not trip.order_ids:
                    continue
                for order_id in trip.order_ids:
                    yield {
                        "task_id": task_id,
                        "warehouse_id": trip.warehouse_id,
                        "clusterization_id": clust_idx,
                        "cluster_id": trip.trip_id,
                        "order_id": order_id,
                        "transport_type": trip.transport_type,
                    }


def _archive_to_serializable(master_archive: Dict[str, List[Any]]) -> dict:
    """Конвертирует List[Individual] в JSON-сериализуемый словарь."""
    result = {}
    for task_key, individuals in master_archive.items():
        result[task_key] = [
            {
                "clusterization_id": clust_idx,
                "fitness_score": ind.fitness_score,
                "is_valid": ind.is_valid,
                "clusters": [
                    {
                        "cluster_id": trip.trip_id,
                        "warehouse_id": trip.warehouse_id,
                        "transport_type": trip.transport_type,
                        "order_ids": list(trip.order_ids),
                    }
                    for trip in ind.trips.values()
                    if trip.order_ids
                ],
            }
            for clust_idx, ind in enumerate(individuals, start=1)
        ]
    return result


def save_clusterizations(
        master_archive: Dict[str, List[Any]],
        base_path: str,
) -> tuple:
    """
    Сохраняет master_archive в JSON и CSV.

    Parameters
    ----------
    master_archive : {f"task_{task_id}": List[Individual]}
    base_path      : путь без расширения, например "data/master_clusterizations"

    Returns
    -------
    (json_path, csv_path)
    """
    base = Path(base_path).with_suffix("")
    base.parent.mkdir(parents=True, exist_ok=True)

    serializable = _archive_to_serializable(master_archive)

    json_path = base.with_suffix(".json")
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2, default=str)

    csv_path = base.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(_iter_csv_rows(master_archive))

    return json_path, csv_path
