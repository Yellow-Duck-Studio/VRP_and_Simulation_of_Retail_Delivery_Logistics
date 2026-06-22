from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from pipeline.serializer import save_pipeline_run
from pipeline.types import ConstraintData, OrderData, PipelineConfig, PipelineRunResult, Solution, TaskContext, TripResult


class PipelineSerializerTest(unittest.TestCase):
    def test_save_pipeline_run_writes_json_and_csv(self) -> None:
        base_time = datetime.fromisoformat("2026-06-07T12:00:00+03:00")
        task_context = TaskContext(
            task_id="1",
            orders=[
                OrderData(1, 1, 55.7000, 37.8000, base_time, base_time + timedelta(minutes=60), 1.0),
                OrderData(2, 1, 55.7010, 37.8010, base_time, base_time + timedelta(minutes=60), 1.0),
                OrderData(3, 2, 55.7020, 37.8020, base_time, base_time + timedelta(minutes=60), 1.0),
            ],
            warehouses={1: (55.6990, 37.7990), 2: (55.6980, 37.7980)},
            constraints=ConstraintData(
                max_order_count=5,
                max_weight_per_transport={"bike": 10.0, "car": 30.0},
                speeds_kmh={"bike": 15.0, "car": 40.0},
                transport_distribution={"car": 1.0},
            ),
        )

        run_result = PipelineRunResult(
            task_id=task_context.task_id,
            pipeline_name="clarke_wright_then_destroy_repair",
            config=PipelineConfig(initializer="clarke_wright"),
            solutions=[
                Solution(
                    solution_id="task_1_clarke_wright_001",
                    pipeline=["clarke_wright"],
                    source_stage="clarke_wright",
                    trips=[
                        TripResult(trip_id=1, warehouse_id=1, transport_type="bike", order_ids=[1, 2]),
                        TripResult(trip_id=2, warehouse_id=2, transport_type="bike", order_ids=[3]),
                    ],
                    metrics=None,
                    metadata={},
                ),
                Solution(
                    solution_id="task_1_clarke_wright_002",
                    pipeline=["clarke_wright"],
                    source_stage="clarke_wright",
                    trips=[
                        TripResult(trip_id=1, warehouse_id=1, transport_type="bike", order_ids=[1]),
                        TripResult(trip_id=2, warehouse_id=1, transport_type="bike", order_ids=[2]),
                    ],
                    metrics=None,
                    metadata={},
                ),
            ],
            summary={},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "result.json"
            save_pipeline_run(run_result, output_path)

            json_path = output_path
            csv_path = output_path.with_suffix(".csv")

            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())

            with json_path.open("r", encoding="utf-8") as file:
                saved_json = json.load(file)
            self.assertEqual(saved_json["task_id"], "1")

            with csv_path.open("r", encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)
                rows = list(reader)

            self.assertEqual(
                reader.fieldnames,
                ["task_id", "warehouse_id", "clusterization_id", "cluster_id", "order_id", "transport_type"],
            )
            self.assertEqual(
                rows,
                [
                    {
                        "task_id": "1",
                        "warehouse_id": "1",
                        "clusterization_id": "1",
                        "cluster_id": "1",
                        "order_id": "1",
                        "transport_type": "bike",
                    },
                    {
                        "task_id": "1",
                        "warehouse_id": "1",
                        "clusterization_id": "1",
                        "cluster_id": "1",
                        "order_id": "2",
                        "transport_type": "bike",
                    },
                    {
                        "task_id": "1",
                        "warehouse_id": "2",
                        "clusterization_id": "1",
                        "cluster_id": "2",
                        "order_id": "3",
                        "transport_type": "bike",
                    },
                    {
                        "task_id": "1",
                        "warehouse_id": "1",
                        "clusterization_id": "2",
                        "cluster_id": "1",
                        "order_id": "1",
                        "transport_type": "bike",
                    },
                    {
                        "task_id": "1",
                        "warehouse_id": "1",
                        "clusterization_id": "2",
                        "cluster_id": "2",
                        "order_id": "2",
                        "transport_type": "bike",
                    },
                ],
            )


if __name__ == "__main__":
    unittest.main()