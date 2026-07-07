"""Гиперпараметры и константы задачи. Тарифы транспорта теперь грузятся из
transport_types.csv через io_utils.load_transport_types — здесь их больше нет."""

MAX_CLUSTER_SIZE = 5

# ---- признаки узла (заказа) ----
# [dist_from_warehouse_km, total_mass_kg, mass_norm,
#  time_window_min, pickup_offset_min, deadline_offset_min]
NODE_FEATURE_DIM = 6

# ---- признаки ребра (пара заказов) ----
# [distance_ij_km, pickup_ready_diff_min, deadline_diff_min, combined_mass_over_min_capacity]
EDGE_FEATURE_DIM = 4

# ---- модель ----
HIDDEN_DIM = 128
NUM_GNN_LAYERS = 4
NUM_HEADS = 4
DROPOUT = 0.1

# ---- обучение ----
LR = 3e-4
WEIGHT_DECAY = 1e-5
EPOCHS = 100
BATCH_SIZE = 32
POS_WEIGHT = 4.0
GRAD_CLIP = 1.0

DEVICE = "cuda"  # "cpu" если нет GPU
SEED = 42
