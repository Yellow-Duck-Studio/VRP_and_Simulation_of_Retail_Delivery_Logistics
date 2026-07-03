from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from experiments.publish import publish_algorithm_run


class PublishRunTest(unittest.TestCase):
    def test_publish_algorithm_run_copies_outputs_and_builds_submission(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_root = root / "runs" / "run_001" / "clarke_wright"
            run_root.mkdir(parents=True, exist_ok=True)
            data_dir = root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)

            (run_root / "master_clusterizations.json").write_text('{"task_1": []}', encoding="utf-8")
            with (run_root / "master_clusterizations.csv").open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=["task_id", "warehouse_id", "clusterization_id", "cluster_id", "order_id", "transport_type"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "task_id": "1",
                        "warehouse_id": "1",
                        "clusterization_id": "1",
                        "cluster_id": "1",
                        "order_id": "1",
                        "transport_type": "car",
                    }
                )

            (data_dir / "warehouses.csv").write_text("task_id,warehouse_id,lat,lon\n1,1,55.7,37.8\n", encoding="utf-8")
            (data_dir / "transport_types.csv").write_text(
                "code,approx_speed_kmh,max_payload_kg,fixed_fee,per_km_fee,per_order_fee,per_kg_min_fee\n"
                "car,40,30,0,0,0,0\n",
                encoding="utf-8",
            )
            (data_dir / "orders.csv").write_text(
                "task_id,order_id,warehouse_id,order_lat,order_lon,pickup_ready_at,created_at,delivery_deadline_at,total_mass_kg\n"
                "1,1,1,55.71,37.81,2026-06-07T12:00:00+03:00,2026-06-07T11:50:00+03:00,2026-06-07T13:00:00+03:00,1.0\n",
                encoding="utf-8",
            )

            target_json, target_csv, submission_path = publish_algorithm_run(
                run_root=root / "runs" / "run_001",
                algorithm_name="clarke_wright",
                data_dir=data_dir,
            )

            self.assertTrue(target_json.exists())
            self.assertTrue(target_csv.exists())
            self.assertTrue(submission_path.exists())


if __name__ == "__main__":
    unittest.main()
