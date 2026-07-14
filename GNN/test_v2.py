from __future__ import annotations

import unittest

import pandas as pd
import torch

from config_v2 import EDGE_FEATURE_DIM, EMBEDDING_DIM, NODE_FEATURE_DIM
from data_v2 import build_graph_v2
from io_utils import TransportTariff, WarehouseInstance
from losses_v2 import combined_embedding_loss
from model_v2 import LogisticsEmbeddingGNNV2
from train_v2 import split_instances_by_task


def _order(order_id, lat, lon, ready, deadline, mass):
    return {
        "order_id": str(order_id),
        "lat": lat,
        "lon": lon,
        "mass_kg": mass,
        "pickup_ready_at": pd.Timestamp(ready),
        "created_at": pd.Timestamp(ready) - pd.Timedelta(minutes=10),
        "delivery_deadline_at": pd.Timestamp(deadline),
    }


def _instance(task_id="1"):
    return WarehouseInstance(
        task_id=task_id,
        warehouse_id="1",
        warehouse_lat=55.75,
        warehouse_lon=37.61,
        orders=[
            _order("1", 55.751, 37.612, "2026-07-01T10:00:00", "2026-07-01T11:00:00", 2.0),
            _order("2", 55.752, 37.613, "2026-07-01T10:05:00", "2026-07-01T11:05:00", 3.0),
            _order("3", 55.740, 37.590, "2026-07-01T12:00:00", "2026-07-01T12:40:00", 9.0),
        ],
        clusters=[["1", "2"], ["3"]],
    )


def _tariffs():
    return [
        TransportTariff("foot", 5.0, 8.0, 0.0, 25.0, 70.0, 0.9),
        TransportTariff("bike", 15.0, 15.0, 40.0, 20.0, 90.0, 0.3),
        TransportTariff("car", 40.0, 50.0, 180.0, 45.0, 130.0, 0.06),
    ]


class LogisticsEmbeddingV2Tests(unittest.TestCase):
    def test_graph_features_are_finite_and_symmetric(self):
        graph = build_graph_v2(_instance(), _tariffs())
        self.assertEqual(tuple(graph.x.shape), (3, NODE_FEATURE_DIM))
        self.assertEqual(tuple(graph.edge_attr.shape), (6, EDGE_FEATURE_DIM))
        self.assertTrue(torch.isfinite(graph.x).all())
        self.assertTrue(torch.isfinite(graph.edge_attr).all())

        by_pair = {}
        for position in range(graph.edge_index.shape[1]):
            pair = tuple(int(value) for value in graph.edge_index[:, position])
            by_pair[pair] = graph.edge_attr[position]
        self.assertTrue(torch.allclose(by_pair[(0, 1)], by_pair[(1, 0)], atol=1e-6))
        self.assertEqual(float(graph.y[0]), 1.0)

    def test_embeddings_are_normalized_and_affinity_is_symmetric(self):
        torch.manual_seed(1)
        graph = build_graph_v2(_instance(), _tariffs())
        model = LogisticsEmbeddingGNNV2().eval()
        logits, embeddings = model(graph, return_embeddings=True)
        self.assertEqual(tuple(embeddings.shape), (3, EMBEDDING_DIM))
        self.assertTrue(torch.allclose(embeddings.norm(dim=1), torch.ones(3), atol=1e-5))

        by_pair = {}
        for position in range(graph.edge_index.shape[1]):
            pair = tuple(int(value) for value in graph.edge_index[:, position])
            by_pair[pair] = logits[position]
        self.assertTrue(torch.allclose(by_pair[(0, 1)], by_pair[(1, 0)], atol=1e-6))

        loss, components = combined_embedding_loss(logits, embeddings, graph.edge_index, graph.y)
        self.assertTrue(torch.isfinite(loss))
        self.assertGreaterEqual(components["pos_weight"], 1.0)

    def test_split_keeps_tasks_separate(self):
        instances = [_instance(str(task_id)) for task_id in range(1, 6)]
        train_instances, validation_instances = split_instances_by_task(instances, validation_fraction=0.4)
        train_tasks = {instance.task_id for instance in train_instances}
        validation_tasks = {instance.task_id for instance in validation_instances}
        self.assertFalse(train_tasks & validation_tasks)
        self.assertTrue(train_tasks)
        self.assertTrue(validation_tasks)


if __name__ == "__main__":
    unittest.main()

