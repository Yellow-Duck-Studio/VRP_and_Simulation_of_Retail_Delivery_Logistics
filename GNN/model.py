"""GNN model with context-aware, normalized order embeddings."""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import TransformerConv

from config import (
    DROPOUT,
    EDGE_FEATURE_DIM,
    HIDDEN_DIM,
    NODE_FEATURE_DIM,
    NUM_GNN_LAYERS,
    NUM_HEADS,
)


class GNNEncoder(nn.Module):
    """Build an order embedding while keeping the existing graph interface."""

    def __init__(self):
        super().__init__()
        self.node_feature_norm = nn.BatchNorm1d(NODE_FEATURE_DIM)
        self.edge_feature_norm = nn.BatchNorm1d(EDGE_FEATURE_DIM)
        self.input_proj = nn.Sequential(
            nn.Linear(NODE_FEATURE_DIM, HIDDEN_DIM),
            nn.GELU(),
            nn.LayerNorm(HIDDEN_DIM),
        )
        self.edge_proj = nn.Sequential(
            nn.Linear(EDGE_FEATURE_DIM, HIDDEN_DIM),
            nn.GELU(),
            nn.LayerNorm(HIDDEN_DIM),
        )

        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()
        for _ in range(NUM_GNN_LAYERS):
            self.convs.append(
                TransformerConv(
                    HIDDEN_DIM,
                    HIDDEN_DIM // NUM_HEADS,
                    heads=NUM_HEADS,
                    edge_dim=HIDDEN_DIM,
                    dropout=DROPOUT,
                )
            )
            self.norms.append(nn.LayerNorm(HIDDEN_DIM))

        self.layer_mix_logits = nn.Parameter(torch.zeros(NUM_GNN_LAYERS + 1))
        self.dropout = nn.Dropout(DROPOUT)
        self.embedding_proj = nn.Sequential(
            nn.Linear(HIDDEN_DIM, HIDDEN_DIM),
            nn.GELU(),
            nn.Dropout(DROPOUT),
            nn.Linear(HIDDEN_DIM, HIDDEN_DIM),
        )

    def forward(self, x, edge_index, edge_attr):
        hidden = self.input_proj(self.node_feature_norm(x))
        projected_edges = self.edge_proj(self.edge_feature_norm(edge_attr))

        layer_states = [hidden]
        for conv, norm in zip(self.convs, self.norms):
            update = conv(hidden, edge_index, projected_edges)
            hidden = norm(hidden + self.dropout(F.gelu(update)))
            layer_states.append(hidden)

        states = torch.stack(layer_states, dim=0)
        weights = torch.softmax(self.layer_mix_logits, dim=0).view(-1, 1, 1)
        mixed_context = (states * weights).sum(dim=0)
        return F.normalize(self.embedding_proj(mixed_context), p=2, dim=-1)


class EdgeAffinityHead(nn.Module):
    """Predict a symmetric same-cluster affinity for each order pair."""

    def __init__(self):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(HIDDEN_DIM * 3 + EDGE_FEATURE_DIM, HIDDEN_DIM),
            nn.GELU(),
            nn.Dropout(DROPOUT),
            nn.Linear(HIDDEN_DIM, HIDDEN_DIM // 2),
            nn.GELU(),
            nn.Linear(HIDDEN_DIM // 2, 1),
        )

    def forward(self, embeddings, edge_index, edge_attr):
        first = embeddings[edge_index[0]]
        second = embeddings[edge_index[1]]
        pair_features = torch.cat(
            [first + second, torch.abs(first - second), first * second, edge_attr],
            dim=-1,
        )
        return self.mlp(pair_features).squeeze(-1)


class ClusteringGNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = GNNEncoder()
        self.affinity_head = EdgeAffinityHead()

    def encode(self, data):
        return self.encoder(data.x, data.edge_index, data.edge_attr)

    def forward(self, data):
        embeddings = self.encode(data)
        return self.affinity_head(embeddings, data.edge_index, data.edge_attr)
