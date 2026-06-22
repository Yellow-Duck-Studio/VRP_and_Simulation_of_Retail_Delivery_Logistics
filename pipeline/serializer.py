from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from pipeline.types import PipelineRunResult


def pipeline_run_to_dict(run_result: PipelineRunResult) -> dict:
    return asdict(run_result)


def pipeline_run_to_csv_rows(run_result: PipelineRunResult) -> list[dict[str, int | str]]:
    rows: list[dict[str, int | str]] = []
    for clusterization_id, solution in enumerate(run_result.solutions, start=1):
        for trip in sorted(solution.trips, key=lambda item: item.trip_id):
            for order_id in trip.order_ids:
                rows.append(
                    {
                        "task_id": run_result.task_id,
                        "warehouse_id": trip.warehouse_id,
                        "clusterization_id": clusterization_id,
                        "cluster_id": trip.trip_id,
                        "order_id": order_id,
                        "transport_type": trip.transport_type,
                    }
                )
    return rows


def save_pipeline_run(run_result: PipelineRunResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(pipeline_run_to_dict(run_result), file, indent=4)

    csv_path = output_path.with_suffix(".csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "task_id",
                "warehouse_id",
                "clusterization_id",
                "cluster_id",
                "order_id",
                "transport_type",
            ],
        )
        writer.writeheader()
        writer.writerows(pipeline_run_to_csv_rows(run_result))
