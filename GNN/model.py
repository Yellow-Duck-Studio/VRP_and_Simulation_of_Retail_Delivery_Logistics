import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import TransformerConv

from config import (
    NODE_FEATURE_DIM,
    EDGE_FEATURE_DIM,
    HIDDEN_DIM,
    NUM_GNN_LAYERS,
    NUM_HEADS,
    DROPOUT,
)


class GNNEncoder(nn.Module):
    """Стек TransformerConv (GAT-подобный, учитывает edge_attr) с residual+LN."""

    def __init__(self):
        super().__init__()
        self.input_proj = nn.Linear(NODE_FEATURE_DIM, HIDDEN_DIM)
        self.edge_proj = nn.Linear(EDGE_FEATURE_DIM, HIDDEN_DIM)

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

    def forward(self, x, edge_index, edge_attr):
        h = self.input_proj(x)
        e = self.edge_proj(edge_attr)
        for conv, norm in zip(self.convs, self.norms):
            h_new = conv(h, edge_index, e)
            h = norm(h + F.relu(h_new))
        return h  # [num_nodes, HIDDEN_DIM]


class EdgeAffinityHead(nn.Module):
    """Предсказывает logit того, что два заказа окажутся в одном кластере."""

    def __init__(self):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(HIDDEN_DIM * 3 + EDGE_FEATURE_DIM, HIDDEN_DIM),
            nn.ReLU(),
            nn.Dropout(DROPOUT),
            nn.Linear(HIDDEN_DIM, HIDDEN_DIM // 2),
            nn.ReLU(),
            nn.Linear(HIDDEN_DIM // 2, 1),
        )

    def forward(self, h, edge_index, edge_attr):
        hi = h[edge_index[0]]
        hj = h[edge_index[1]]
        feat = torch.cat([hi, hj, torch.abs(hi - hj), edge_attr], dim=-1)
        return self.mlp(feat).squeeze(-1)  # [num_edges]


class ClusteringGNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = GNNEncoder()
        self.affinity_head = EdgeAffinityHead()

    def forward(self, data):
        h = self.encoder(data.x, data.edge_index, data.edge_attr)
        logits = self.affinity_head(h, data.edge_index, data.edge_attr)
        return logits  # [num_edges], сырые логиты (sigmoid -> вероятность "один кластер")
