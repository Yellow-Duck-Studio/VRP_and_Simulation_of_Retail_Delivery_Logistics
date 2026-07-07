"""
Гео-утилиты.

haversine_km — точное расстояние по сфере (используется в costs.py для
реального расчёта cost, чтобы совпадать с тем, как считает солвер).

to_local_km — приближённая равнопромежуточная (equirectangular) проекция
lat/lon в локальные метры/км относительно точки отсчёта (обычно склад).
Годится ТОЛЬКО для GNN-фич и эвристик (кластер компактный, в пределах
одного города, искажение пренебрежимо мало) — не для итогового cost.
"""

import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def to_local_km(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple:
    """Equirectangular проекция: x — направление на восток, y — на север, в км."""
    dlat = math.radians(lat - ref_lat)
    dlon = math.radians(lon - ref_lon)
    x = dlon * math.cos(math.radians(ref_lat)) * EARTH_RADIUS_KM
    y = dlat * EARTH_RADIUS_KM
    return x, y
