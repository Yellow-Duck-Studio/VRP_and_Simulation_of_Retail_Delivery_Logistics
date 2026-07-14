"""Logistics-aware order embeddings and symmetric pair affinities."""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import TransformerConv

from config_v2 import (
    DROPOUT,
    EDGE_FEATURE_DIM,
    EMBEDDING_DIM,
    HIDDEN_DIM,
    NODE_FEATURE_DIM,
    NUM_GNN_LAYERS,
    NUM_HEADS,
)


class LogisticsEncoderV2(nn.Module):
    def __init__(self):
        super().__init__()
        self.node_projection = nn.Sequential(
            nn.Linear(NODE_FEATURE_DIM, HIDDEN_DIM),
            nn.GELU(),
            nn.LayerNorm(HIDDEN_DIM),
        )
        self.edge_projection = nn.Sequential(
            nn.Linear(EDGE_FEATURE_DIM, HIDDEN_DIM),
            nn.GELU(),
            nn.LayerNorm(HIDDEN_DIM),
        )
        self.layers = nn.ModuleList(
            [
                TransformerConv(
                    HIDDEN_DIM,
                    HIDDEN_DIM // NUM_HEADS,
                    heads=NUM_HEADS,
                    edge_dim=HIDDEN_DIM,
                    dropout=DROPOUT,
                )
                for _ in range(NUM_GNN_LAYERS)
            ]
        )
        self.norms = nn.ModuleList([nn.LayerNorm(HIDDEN_DIM) for _ in range(NUM_GNN_LAYERS)])
        self.dropout = nn.Dropout(DROPOUT)
        self.embedding_projection = nn.Linear(HIDDEN_DIM, EMBEDDING_DIM)

    def forward(self, x, edge_index, edge_attr):
        hidden = self.node_projection(x)
        projected_edges = self.edge_projection(edge_attr)
        for layer, norm in zip(self.layers, self.norms):
            update = layer(hidden, edge_index, projected_edges)
            hidden = norm(hidden + self.dropout(F.gelu(update)))
        return F.normalize(self.embedding_projection(hidden), p=2, dim=-1)


class SymmetricAffinityHeadV2(nn.Module):
    def __init__(self):
        super().__init__()
        input_dim = EMBEDDING_DIM * 3 + EDGE_FEATURE_DIM
        self.network = nn.Sequential(
            nn.Linear(input_dim, HIDDEN_DIM),
            nn.GELU(),
            nn.Dropout(DROPOUT),
            nn.Linear(HIDDEN_DIM, HIDDEN_DIM // 2),
            nn.GELU(),
            nn.Linear(HIDDEN_DIM // 2, 1),
        )

    def forward(self, embeddings, edge_index, edge_attr):
        first = embeddings[edge_index[0]]
        second = embeddings[edge_index[1]]
        symmetric_features = torch.cat(
            [first + second, torch.abs(first - second), first * second, edge_attr], dim=-1
        )
        return self.network(symmetric_features).squeeze(-1)


class LogisticsEmbeddingGNNV2(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = LogisticsEncoderV2()
        self.affinity_head = SymmetricAffinityHeadV2()

    def encode(self, data):
        return self.encoder(data.x, data.edge_index, data.edge_attr)

    def forward(self, data, return_embeddings: bool = False):
        embeddings = self.encode(data)
        logits = self.affinity_head(embeddings, data.edge_index, data.edge_attr)
        if return_embeddings:
            return logits, embeddings
        return logits

