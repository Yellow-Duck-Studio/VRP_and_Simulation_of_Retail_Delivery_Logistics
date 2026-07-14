"""Строит полносвязный граф заказов одного склада, признаки в km/минутах."""

import torch
from torch_geometric.data import Data

from config import NODE_FEATURE_DIM, EDGE_FEATURE_DIM
from geo import haversine_km
from io_utils import WarehouseInstance


def build_graph(inst: WarehouseInstance, default_max_couriers: int) -> Data:
    orders = inst.orders
    n = len(orders)
    wlat, wlon = inst.warehouse_lat, inst.warehouse_lon

    masses = [o["mass_kg"] for o in orders]
    max_mass = max(masses) if masses else 1.0
    min_pickup = min(o["pickup_ready_at"] for o in orders)

    # Глобальный (не per-order) параметр -- одно и то же значение
    # дублируется в каждую ноду, чтобы не менять архитектуру модели
    # отдельным "global feature" входом. Источник: inst.max_couriers, если
    # он известен (сгенерирован обновлённым brute_force_ilp.py), иначе
    # fallback на default_max_couriers (например, для старых данных без
    # этого поля).
    max_couriers = inst.max_couriers if inst.max_couriers is not None else default_max_couriers

    node_feats = []
    for o in orders:
        dist_wh = haversine_km(wlat, wlon, o["lat"], o["lon"])
        time_window_min = (o["delivery_deadline_at"] - o["pickup_ready_at"]).total_seconds() / 60.0
        pickup_offset_min = (o["pickup_ready_at"] - min_pickup).total_seconds() / 60.0
        deadline_offset_min = (o["delivery_deadline_at"] - min_pickup).total_seconds() / 60.0
        node_feats.append(
            [
                dist_wh,
                o["mass_kg"],
                o["mass_kg"] / max(max_mass, 1e-6),
                time_window_min,
                pickup_offset_min,
                deadline_offset_min,
                float(max_couriers),
            ]
        )
    x = torch.tensor(node_feats, dtype=torch.float)
    assert x.shape[1] == NODE_FEATURE_DIM

    edge_index = []
    edge_attr = []
    min_capacity = 1.0  # подставится реальный min(max_payload_kg) на этапе тренировки/инференса
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            oi, oj = orders[i], orders[j]
            dist_ij = haversine_km(oi["lat"], oi["lon"], oj["lat"], oj["lon"])
            pickup_diff = abs((oi["pickup_ready_at"] - oj["pickup_ready_at"]).total_seconds()) / 60.0
            deadline_diff = abs((oi["delivery_deadline_at"] - oj["delivery_deadline_at"]).total_seconds()) / 60.0
            combined_mass = oi["mass_kg"] + oj["mass_kg"]
            edge_index.append([i, j])
            edge_attr.append([dist_ij, pickup_diff, deadline_diff, combined_mass])

    edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()
    edge_attr = torch.tensor(edge_attr, dtype=torch.float)
    assert edge_attr.shape[1] == EDGE_FEATURE_DIM

    data = Data(x=x, edge_index=edge_index, edge_attr=edge_attr)
    data.order_ids = [o["order_id"] for o in orders]  # список str, не тензор
    data.num_orders = n
    data.warehouse_lat = wlat
    data.warehouse_lon = wlon

    if inst.clusters is not None:
        id_to_cluster = {}
        for c_idx, cluster in enumerate(inst.clusters):
            for oid in cluster:
                id_to_cluster[oid] = c_idx
        y = []
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                same = id_to_cluster.get(orders[i]["order_id"]) == id_to_cluster.get(orders[j]["order_id"])
                y.append(1.0 if same else 0.0)
        data.y = torch.tensor(y, dtype=torch.float)

    return data


def normalize_edge_mass(edge_attr, min_capacity_kg: float):
    """Делит 4-ю колонку edge_attr (combined_mass) на min_capacity_kg, чтобы
    получить безразмерный признак "насколько кластер близок к пределу
    вместимости самого маленького транспорта". Вызывается один раз после
    build_graph, когда известен список тарифов (см. data.py::WarehouseGraphDataset)."""
    edge_attr = edge_attr.clone()
    edge_attr[:, 3] = edge_attr[:, 3] / max(min_capacity_kg, 1e-6)
    return edge_attr


class WarehouseGraphDataset(torch.utils.data.Dataset):
    def __init__(self, instances, min_capacity_kg: float, default_max_couriers: int):
        self.instances = [inst for inst in instances if len(inst.orders) >= 2]
        self.min_capacity_kg = min_capacity_kg
        self.default_max_couriers = default_max_couriers

    def __len__(self):
        return len(self.instances)

    def __getitem__(self, idx):
        data = build_graph(self.instances[idx], self.default_max_couriers)
        data.edge_attr = normalize_edge_mass(data.edge_attr, self.min_capacity_kg)
        return data