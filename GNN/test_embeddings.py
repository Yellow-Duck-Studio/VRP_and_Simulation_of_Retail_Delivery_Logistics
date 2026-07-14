from __future__ import annotations

import unittest

import torch
import torch.nn.functional as F
from torch_geometric.data import Data

from config import EDGE_FEATURE_DIM, HIDDEN_DIM, NODE_FEATURE_DIM
from model import ClusteringGNN


def _complete_graph(node_count: int) -> Data:
    edge_index = []
    edge_features = []
    pair_features = {}
    generator = torch.Generator().manual_seed(7)

    for first in range(node_count):
        for second in range(node_count):
            if first == second:
                continue
            pair = tuple(sorted((first, second)))
            if pair not in pair_features:
                pair_features[pair] = torch.randn(EDGE_FEATURE_DIM, generator=generator)
            edge_index.append([first, second])
            edge_features.append(pair_features[pair])

    return Data(
        x=torch.randn(node_count, NODE_FEATURE_DIM, generator=generator),
        edge_index=torch.tensor(edge_index, dtype=torch.long).t().contiguous(),
        edge_attr=torch.stack(edge_features),
    )


class EmbeddingEncoderTests(unittest.TestCase):
    def test_existing_forward_api_and_normalized_embeddings(self):
        graph = _complete_graph(4)
        model = ClusteringGNN().eval()

        with torch.no_grad():
            embeddings = model.encode(graph)
            logits = model(graph)

        self.assertEqual(tuple(embeddings.shape), (4, HIDDEN_DIM))
        self.assertEqual(tuple(logits.shape), (12,))
        self.assertTrue(torch.allclose(embeddings.norm(dim=1), torch.ones(4), atol=1e-5))

    def test_affinity_is_symmetric(self):
        graph = _complete_graph(4)
        model = ClusteringGNN().eval()

        with torch.no_grad():
            logits = model(graph)

        by_pair = {}
        for position in range(graph.edge_index.shape[1]):
            first = int(graph.edge_index[0, position])
            second = int(graph.edge_index[1, position])
            by_pair[(first, second)] = logits[position]

        for first in range(4):
            for second in range(first + 1, 4):
                self.assertTrue(
                    torch.allclose(by_pair[(first, second)], by_pair[(second, first)], atol=1e-6)
                )

    def test_existing_training_loss_can_backpropagate(self):
        graph = _complete_graph(4)
        model = ClusteringGNN().train()
        targets = torch.tensor([0.0, 1.0] * 6)

        logits = model(graph)
        loss = F.binary_cross_entropy_with_logits(logits, targets)
        loss.backward()

        self.assertTrue(torch.isfinite(loss))
        self.assertTrue(any(parameter.grad is not None for parameter in model.parameters()))


if __name__ == "__main__":
    unittest.main()
