"""Metrics that remain informative for strongly imbalanced edge labels."""

from __future__ import annotations

import torch


def average_precision(targets: torch.Tensor, scores: torch.Tensor) -> float:
    positives = int(targets.sum().item())
    if positives == 0:
        return 0.0
    order = torch.argsort(scores, descending=True)
    sorted_targets = targets[order]
    true_positives = torch.cumsum(sorted_targets, dim=0)
    ranks = torch.arange(1, len(sorted_targets) + 1, device=targets.device)
    precision_at_rank = true_positives / ranks
    return float((precision_at_rank * sorted_targets).sum().item() / positives)


def classification_metrics(
    logits: torch.Tensor,
    targets: torch.Tensor,
    threshold: float = 0.5,
) -> dict[str, float]:
    probabilities = torch.sigmoid(logits)
    predictions = probabilities >= threshold
    positives = targets > 0.5
    negatives = ~positives

    tp = int((predictions & positives).sum().item())
    fp = int((predictions & negatives).sum().item())
    fn = int((~predictions & positives).sum().item())
    tn = int((~predictions & negatives).sum().item())

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    specificity = tn / max(tn + fp, 1)
    f1 = 2.0 * precision * recall / max(precision + recall, 1e-12)
    return {
        "average_precision": average_precision(targets.float(), probabilities),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "balanced_accuracy": (recall + specificity) / 2.0,
        "positive_share": float(positives.float().mean().item()) if targets.numel() else 0.0,
        "tp": float(tp),
        "fp": float(fp),
        "fn": float(fn),
        "tn": float(tn),
    }


def find_best_f1_threshold(logits: torch.Tensor, targets: torch.Tensor) -> tuple[float, dict[str, float]]:
    best_threshold = 0.5
    best_metrics = classification_metrics(logits, targets, threshold=best_threshold)
    for step in range(5, 100, 5):
        threshold = step / 100.0
        candidate = classification_metrics(logits, targets, threshold=threshold)
        if candidate["f1"] > best_metrics["f1"]:
            best_threshold = threshold
            best_metrics = candidate
    best_metrics["threshold"] = best_threshold
    return best_threshold, best_metrics
