import argparse
import random

import torch
import torch.nn as nn
from torch_geometric.loader import DataLoader

from config import LR, WEIGHT_DECAY, EPOCHS, BATCH_SIZE, POS_WEIGHT, GRAD_CLIP, DEVICE, SEED
from io_utils import load_instances, load_transport_types
from data import WarehouseGraphDataset
from model import ClusteringGNN


def set_seed(seed: int):
    random.seed(seed)
    torch.manual_seed(seed)


def evaluate(model, loader, device):
    model.eval()
    total_loss, total_edges, correct = 0.0, 0, 0
    loss_fn = nn.BCEWithLogitsLoss(reduction="sum")
    with torch.no_grad():
        for batch in loader:
            batch = batch.to(device)
            logits = model(batch)
            loss = loss_fn(logits, batch.y)
            total_loss += loss.item()
            total_edges += batch.y.numel()
            pred = (torch.sigmoid(logits) > 0.5).float()
            correct += (pred == batch.y).sum().item()
    return total_loss / max(total_edges, 1), correct / max(total_edges, 1)


def train(warehouses_csv, orders_csv, transport_csv, solutions_json, out_path="model.pt"):
    set_seed(SEED)
    device = torch.device(DEVICE if torch.cuda.is_available() else "cpu")

    tariffs = load_transport_types(transport_csv)
    min_capacity_kg = min(t.max_payload_kg for t in tariffs)

    instances = load_instances(warehouses_csv, orders_csv, solutions_json)
    instances = [inst for inst in instances if inst.clusters is not None]
    if not instances:
        raise RuntimeError("Ни одного инстанса с ground-truth разбиением не найдено — проверь solutions.json")

    random.shuffle(instances)
    split = max(1, int(0.9 * len(instances)))
    train_ds = WarehouseGraphDataset(instances[:split], min_capacity_kg)
    val_ds = WarehouseGraphDataset(instances[split:] or instances[-1:], min_capacity_kg)
    print(f"train warehouses: {len(train_ds)}, val warehouses: {len(val_ds)}")

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False)

    model = ClusteringGNN().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(POS_WEIGHT, device=device))

    best_val_loss = float("inf")
    for epoch in range(1, EPOCHS + 1):
        model.train()
        running = 0.0
        for batch in train_loader:
            batch = batch.to(device)
            optimizer.zero_grad()
            logits = model(batch)
            loss = loss_fn(logits, batch.y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
            optimizer.step()
            running += loss.item() * batch.y.numel()
        scheduler.step()

        val_loss, val_acc = evaluate(model, val_loader, device)
        print(f"epoch {epoch:03d} | train_loss {running/len(train_ds):.4f} "
              f"| val_loss {val_loss:.4f} | val_edge_acc {val_acc:.4f}")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), out_path)
            print(f"  -> saved best model to {out_path}")

    return model


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouses", required=True)
    parser.add_argument("--orders", required=True)
    parser.add_argument("--transport", required=True)
    parser.add_argument("--solutions", required=True)
    parser.add_argument("--out", default="model.pt")
    args = parser.parse_args()
    train(args.warehouses, args.orders, args.transport, args.solutions, args.out)
