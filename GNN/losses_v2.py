"""Losses for imbalanced affinity labels and useful embedding geometry."""

from __future__ import annotations

import torch
import torch.nn.functional as F

from config_v2 import (
    CONTRASTIVE_MARGIN,
    CONTRASTIVE_WEIGHT,
    FOCAL_GAMMA,
    HARD_NEGATIVE_RATIO,
    MAX_POS_WEIGHT,
)


def balanced_focal_loss(
    logits: torch.Tensor,
    targets: torch.Tensor,
    gamma: float = FOCAL_GAMMA,
    max_pos_weight: float = MAX_POS_WEIGHT,
) -> tuple[torch.Tensor, float]:
    positives = targets.sum()
    negatives = targets.numel() - positives
    ratio = negatives / positives.clamp_min(1.0)
    pos_weight = ratio.clamp(min=1.0, max=max_pos_weight)
    base_loss = F.binary_cross_entropy_with_logits(
        logits, targets, pos_weight=pos_weight, reduction="none"
    )
    probabilities = torch.sigmoid(logits)
    target_probability = probabilities * targets + (1.0 - probabilities) * (1.0 - targets)
    focal_factor = (1.0 - target_probability).pow(gamma)
    return (base_loss * focal_factor).mean(), float(pos_weight.detach().cpu())


def edge_contrastive_loss(
    embeddings: torch.Tensor,
    edge_index: torch.Tensor,
    targets: torch.Tensor,
    margin: float = CONTRASTIVE_MARGIN,
    hard_negative_ratio: int = HARD_NEGATIVE_RATIO,
) -> torch.Tensor:
    unique = edge_index[0] < edge_index[1]
    if not unique.any():
        return embeddings.sum() * 0.0

    first = embeddings[edge_index[0, unique]]
    second = embeddings[edge_index[1, unique]]
    similarities = (first * second).sum(dim=-1)
    unique_targets = targets[unique]

    positive_similarities = similarities[unique_targets > 0.5]
    negative_similarities = similarities[unique_targets <= 0.5]
    positive_loss = (
        (1.0 - positive_similarities).pow(2).mean()
        if positive_similarities.numel()
        else similarities.sum() * 0.0
    )

    if negative_similarities.numel():
        requested = max(1, positive_similarities.numel() * hard_negative_ratio)
        hard_count = min(int(requested), negative_similarities.numel())
        hard_negatives = torch.topk(negative_similarities, k=hard_count).values
        negative_loss = F.relu(hard_negatives - margin).pow(2).mean()
    else:
        negative_loss = similarities.sum() * 0.0

    return positive_loss + negative_loss


def combined_embedding_loss(
    logits: torch.Tensor,
    embeddings: torch.Tensor,
    edge_index: torch.Tensor,
    targets: torch.Tensor,
) -> tuple[torch.Tensor, dict[str, float]]:
    affinity_loss, pos_weight = balanced_focal_loss(logits, targets)
    contrastive_loss = edge_contrastive_loss(embeddings, edge_index, targets)
    total_loss = (1.0 - CONTRASTIVE_WEIGHT) * affinity_loss + CONTRASTIVE_WEIGHT * contrastive_loss
    return total_loss, {
        "affinity_loss": float(affinity_loss.detach().cpu()),
        "contrastive_loss": float(contrastive_loss.detach().cpu()),
        "pos_weight": pos_weight,
    }

