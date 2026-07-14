"""Export order embeddings and pair affinities without constructing clusters."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from config_v2 import DEVICE, MODEL_VERSION
from data_v2 import build_graph_v2
from io_utils import load_instances, load_transport_types_with_optional_couriers
from model_v2 import LogisticsEmbeddingGNNV2


def load_model(checkpoint_path: str, device) -> tuple[LogisticsEmbeddingGNNV2, float]:
    checkpoint = torch.load(checkpoint_path, map_location=device)
    if checkpoint.get("model_version") != MODEL_VERSION:
        raise ValueError(
            f"Expected checkpoint version '{MODEL_VERSION}', got '{checkpoint.get('model_version')}'"
        )
    model = LogisticsEmbeddingGNNV2().to(device)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    threshold = float(checkpoint.get("validation_metrics", {}).get("threshold", 0.5))
    return model, threshold


def export_embeddings(
    warehouses_csv: str,
    orders_csv: str,
    transport_csv: str,
    model_path: str,
    output_path: str,
    couriers_csv: str | None = None,
) -> list[dict]:
    device = torch.device(DEVICE if torch.cuda.is_available() else "cpu")
    tariffs = load_transport_types_with_optional_couriers(transport_csv, couriers_csv=couriers_csv)
    instances = load_instances(warehouses_csv, orders_csv, solutions_json=None)
    model, recommended_threshold = load_model(model_path, device)
    exported = []

    with torch.no_grad():
        for instance in instances:
            graph = build_graph_v2(instance, tariffs).to(device)
            logits, embeddings = model(graph, return_embeddings=True)
            probabilities = torch.sigmoid(logits)
            unique_edges = graph.edge_index[0] < graph.edge_index[1]
            edge_positions = torch.nonzero(unique_edges, as_tuple=False).flatten().tolist()
            order_ids = [str(order["order_id"]) for order in instance.orders]

            affinities = []
            for position in edge_positions:
                first_index = int(graph.edge_index[0, position])
                second_index = int(graph.edge_index[1, position])
                affinities.append(
                    {
                        "order_id_a": order_ids[first_index],
                        "order_id_b": order_ids[second_index],
                        "affinity": round(float(probabilities[position].cpu()), 8),
                    }
                )

            exported.append(
                {
                    "task_id": str(instance.task_id),
                    "warehouse_id": str(instance.warehouse_id),
                    "model_version": MODEL_VERSION,
                    "embedding_dim": embeddings.shape[1],
                    "recommended_affinity_threshold": recommended_threshold,
                    "orders": [
                        {
                            "order_id": order_id,
                            "embedding": [round(float(value), 8) for value in embeddings[index].cpu()],
                        }
                        for index, order_id in enumerate(order_ids)
                    ],
                    "affinities": affinities,
                }
            )
            print(
                f"task={instance.task_id} warehouse={instance.warehouse_id}: "
                f"{len(order_ids)} embeddings, {len(affinities)} affinities"
            )

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(exported, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(exported)} warehouse graphs to {target}")
    return exported


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouses", default="data/large/warehouses.csv")
    parser.add_argument("--orders", default="data/large/orders.csv")
    parser.add_argument("--transport", default="data/transport_types.csv")
    parser.add_argument("--couriers", default=None)
    parser.add_argument("--model", default="GNN/model_v2.pt")
    parser.add_argument("--out", default="data/embeddings_v2.json")
    arguments = parser.parse_args()
    export_embeddings(
        arguments.warehouses,
        arguments.orders,
        arguments.transport,
        arguments.model,
        arguments.out,
        arguments.couriers,
    )
