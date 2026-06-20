from datetime import datetime, timedelta
import unittest

from pipeline.runner import run_pipeline
from pipeline.types import ConstraintData, OrderData, PipelineConfig, TaskContext


class PipelineSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        base_time = datetime.fromisoformat("2026-06-07T12:00:00+03:00")
        self.task_context = TaskContext(
            task_id="demo",
            orders=[
                OrderData(1, 1, 55.7000, 37.8000, base_time, base_time + timedelta(minutes=60), 1.0),
                OrderData(2, 1, 55.7010, 37.8010, base_time, base_time + timedelta(minutes=60), 1.0),
                OrderData(3, 1, 55.7020, 37.8020, base_time, base_time + timedelta(minutes=60), 1.0),
            ],
            warehouses={1: (55.6990, 37.7990)},
            constraints=ConstraintData(
                max_order_count=5,
                max_weight_per_transport={"bike": 10.0, "foot": 10.0, "car": 30.0},
                speeds_kmh={"bike": 15.0, "foot": 5.0, "car": 40.0},
                transport_distribution={"car": 1.0, "bike": 0.0, "foot": 0.0},
            ),
        )

    def test_clarke_then_destroy_repair_pipeline(self) -> None:
        config = PipelineConfig(
            initializer="clarke_wright",
            improver="destroy_repair",
            improver_config={
                "iterations": 20,
                "destroy_fraction": 0.2,
                "max_solutions": 10,
                "rng_seed": 42,
            },
            max_solutions=10,
        )

        result = run_pipeline(self.task_context, config)

        self.assertEqual(result.pipeline_name, "clarke_wright_then_destroy_repair")
        self.assertGreaterEqual(len(result.solutions), 1)
        self.assertTrue(all(solution.metrics is not None for solution in result.solutions))
        self.assertTrue(all(solution.metrics.is_valid for solution in result.solutions))


if __name__ == "__main__":
    unittest.main()
