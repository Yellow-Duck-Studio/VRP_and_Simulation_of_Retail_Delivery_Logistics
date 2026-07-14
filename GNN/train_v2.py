"""Train logistics-aware embeddings without constructing final clusters."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import torch
from torch_geometric.loader import DataLoader

from config_v2 import (
    BATCH_SIZE,
    DEVICE,
    EDGE_FEATURE_DIM,
    EMBEDDING_DIM,
    EPOCHS,
    GRAD_CLIP,
    LR,
    MODEL_VERSION,
    NODE_FEATURE_DIM,
    SEED,
    VALIDATION_FRACTION,
    WEIGHT_DECAY,
)
from data_v2 import WarehouseGraphDatasetV2
from io_utils import load_instances, load_transport_types_with_optional_couriers
from losses_v2 import combined_embedding_loss
from metrics_v2 import find_best_f1_threshold
from model_v2 import LogisticsEmbeddingGNNV2


def set_seed(seed: int = SEED) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def split_instances_by_task(instances, validation_fraction: float = VALIDATION_FRACTION, seed: int = SEED):
    task_ids = sorted({str(instance.task_id) for instance in instances})
    if len(task_ids) < 2:
        split_index = max(1, len(instances) - 1)
        return instances[:split_index], instances[split_index:] or instances[-1:]

    rng = random.Random(seed)
    rng.shuffle(task_ids)
    validation_count = max(1, round(len(task_ids) * validation_fraction))
    validation_tasks = set(task_ids[:validation_count])
    train_instances = [instance for instance in instances if str(instance.task_id) not in validation_tasks]
    validation_instances = [instance for instance in instances if str(instance.task_id) in validation_tasks]
    return train_instances, validation_instances


def _unique_edges(logits, targets, edge_index):
    unique = edge_index[0] < edge_index[1]
    return logits[unique], targets[unique]


def evaluate(model, loader, device) -> dict[str, float]:
    model.eval()
    total_loss = 0.0
    batches = 0
    all_logits = []
    all_targets = []

    with torch.no_grad():
        for batch in loader:
            batch = batch.to(device)
            logits, embeddings = model(batch, return_embeddings=True)
            loss, _ = combined_embedding_loss(logits, embeddings, batch.edge_index, batch.y)
            unique_logits, unique_targets = _unique_edges(logits, batch.y, batch.edge_index)
            all_logits.append(unique_logits.cpu())
            all_targets.append(unique_targets.cpu())
            total_loss += float(loss.cpu())
            batches += 1

    if not all_logits:
        return {"loss": 0.0, "average_precision": 0.0, "f1": 0.0}
    _, metrics = find_best_f1_threshold(torch.cat(all_logits), torch.cat(all_targets))
    metrics["loss"] = total_loss / max(batches, 1)
    return metrics


def _save_checkpoint(path: str, model, epoch: int, metrics: dict[str, float]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_version": MODEL_VERSION,
            "state_dict": model.state_dict(),
            "epoch": epoch,
            "validation_metrics": metrics,
            "node_feature_dim": NODE_FEATURE_DIM,
            "edge_feature_dim": EDGE_FEATURE_DIM,
            "embedding_dim": EMBEDDING_DIM,
        },
        output_path,
    )


def train(
    warehouses_csv: str,
    orders_csv: str,
    transport_csv: str,
    solutions_json: str,
    out_path: str = "GNN/model_v2.pt",
    couriers_csv: str | None = None,
    epochs: int = EPOCHS,
):
    set_seed()
    device = torch.device(DEVICE if torch.cuda.is_available() else "cpu")
    tariffs = load_transport_types_with_optional_couriers(transport_csv, couriers_csv=couriers_csv)
    instances = [
        instance
        for instance in load_instances(warehouses_csv, orders_csv, solutions_json)
        if instance.clusters is not None and len(instance.orders) >= 2
    ]
    if not instances:
        raise RuntimeError("No labeled warehouse instances were found")

    train_instances, validation_instances = split_instances_by_task(instances)
    train_tasks = sorted({str(instance.task_id) for instance in train_instances})
    validation_tasks = sorted({str(instance.task_id) for instance in validation_instances})
    print(f"Model: {MODEL_VERSION}")
    print(f"Device: {device}")
    print(f"Train tasks: {train_tasks} ({len(train_instances)} warehouses)")
    print(f"Validation tasks: {validation_tasks} ({len(validation_instances)} warehouses)")
    print("Building and caching logistics graphs...")

    train_dataset = WarehouseGraphDatasetV2(train_instances, tariffs)
    validation_dataset = WarehouseGraphDatasetV2(validation_instances, tariffs)
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
    validation_loader = DataLoader(validation_dataset, batch_size=BATCH_SIZE, shuffle=False)

    train_labels = torch.cat([graph.y[graph.edge_index[0] < graph.edge_index[1]] for graph in train_dataset.graphs])
    positive_count = int(train_labels.sum().item())
    print(
        f"Train pairs: {train_labels.numel()}, positive: {positive_count} "
        f"({positive_count / max(train_labels.numel(), 1):.2%})"
    )

    model = LogisticsEmbeddingGNNV2().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(epochs, 1))
    best_average_precision = -1.0

    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        running_affinity = 0.0
        running_contrastive = 0.0
        batches = 0

        for batch in train_loader:
            batch = batch.to(device)
            optimizer.zero_grad()
            logits, embeddings = model(batch, return_embeddings=True)
            loss, components = combined_embedding_loss(logits, embeddings, batch.edge_index, batch.y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
            optimizer.step()
            running_loss += float(loss.detach().cpu())
            running_affinity += components["affinity_loss"]
            running_contrastive += components["contrastive_loss"]
            batches += 1

        scheduler.step()
        validation = evaluate(model, validation_loader, device)
        print(
            f"epoch {epoch:03d} | train {running_loss / max(batches, 1):.4f} "
            f"(aff {running_affinity / max(batches, 1):.4f}, "
            f"emb {running_contrastive / max(batches, 1):.4f}) | "
            f"val {validation['loss']:.4f} | AP {validation['average_precision']:.4f} | "
            f"F1 {validation['f1']:.4f} | P {validation.get('precision', 0.0):.4f} | "
            f"R {validation.get('recall', 0.0):.4f} | threshold {validation.get('threshold', 0.5):.2f}"
        )

        if validation["average_precision"] > best_average_precision:
            best_average_precision = validation["average_precision"]
            _save_checkpoint(out_path, model, epoch, validation)
            print(f"  -> saved best checkpoint to {out_path}")

    return model


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouses", default="data/large/warehouses.csv")
    parser.add_argument("--orders", default="data/large/orders.csv")
    parser.add_argument("--transport", default="data/transport_types.csv")
    parser.add_argument("--solutions", default="data/large/ilp_master.json")
    parser.add_argument("--couriers", default=None)
    parser.add_argument("--out", default="GNN/model_v2.pt")
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    arguments = parser.parse_args()
    train(
        arguments.warehouses,
        arguments.orders,
        arguments.transport,
        arguments.solutions,
        arguments.out,
        arguments.couriers,
        arguments.epochs,
    )
