#!/usr/bin/env python3
"""
enrich_dataset.py
==================

Builds enriched datasets from the raw clustering-task CSVs.

This script is standalone and reusable: point it at any directory containing
the five raw CSVs (matching the schema below) and it will produce
`enriched_orders.csv` and `enriched_warehouses.csv` in an output directory.
It does not depend on any other module or pre-generated data.

Required input files (in --input-dir):
  - orders.csv
        columns: task_id, order_id, warehouse_id, order_lat, order_lon,
                 pickup_ready_at, created_at, delivery_deadline_at, total_mass_kg
  - warehouses.csv
        columns: task_id, warehouse_id, lat, lon
  - transport_types.csv
        columns: code, approx_speed_kmh, max_payload_kg
        (code values can be either foot/bike/car or walking/moped/car)

Optional input file:
  - warehouse_time_estimates.csv
        columns: task_id, courier_id, warehouse_id, estimated_duration_sec
        If present, enriched_warehouses.csv gets WTE summary stats.
        If absent, enriched_warehouses.csv is just a copy of warehouses.csv.

Output files (in --output-dir):
  - enriched_orders.csv      — orders + derived time/distance/feasibility columns
  - enriched_warehouses.csv  — warehouses + WTE summary stats (if available)

Derived columns added to enriched_orders.csv
----------------------------------------------
  time_window_sec            deadline - pickup_ready, in seconds
  lead_time_sec               deadline - created_at, in seconds
  prep_time_sec                pickup_ready - created_at, in seconds
  pickup_ready_ts              pickup_ready_at as a Unix timestamp (UTC)
  deadline_ts                   delivery_deadline_at as a Unix timestamp (UTC)
  dist_from_warehouse_km        haversine distance order <-> its warehouse
  straight_line_travel_sec_*    dist_from_warehouse_km / speed, per transport type
  feasible_solo_*               True if straight_line_travel_sec_* < time_window_sec
                                 (i.e. a solo courier of that type could make it
                                 on a direct line, ignoring real road network)

* = normalized transport type name: walking / moped / car
  (raw codes foot/bike/car are mapped to walking/moped accordingly)

Derived columns added to enriched_warehouses.csv (if WTE file is provided)
----------------------------------------------------------------------------
  wte_mean, wte_min, wte_max     stats over estimated_duration_sec for all
                                   couriers that have an estimate for this
                                   (task_id, warehouse_id)
  n_couriers_in_range            count of couriers with an estimate

Usage
-----
  python enrich_dataset.py --input-dir /path/to/raw --output-dir /path/to/out

  python enrich_dataset.py                      # defaults to current directory
                                                 # for both input and output
"""

import argparse
import sys
from math import radians, cos, sin, asin, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

# Map raw transport codes -> spec names. Accepts either naming convention,
# case-insensitively. Unknown codes pass through unchanged (lowercased).
TRANSPORT_ALIASES = {
    "foot": "walking",
    "walking": "walking",
    "bike": "moped",
    "moped": "moped",
    "car": "car",
}

REQUIRED_ORDER_COLS = [
    "task_id", "order_id", "warehouse_id", "order_lat", "order_lon",
    "pickup_ready_at", "created_at", "delivery_deadline_at", "total_mass_kg",
]
REQUIRED_WAREHOUSE_COLS = ["task_id", "warehouse_id", "lat", "lon"]
REQUIRED_TRANSPORT_COLS = ["code", "approx_speed_kmh", "max_payload_kg"]


def normalize_transport_code(code: str) -> str:
    return TRANSPORT_ALIASES.get(str(code).strip().lower(), str(code).strip().lower())


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in km between two lat/lon points."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


def check_columns(df: pd.DataFrame, required: list, name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"{name} is missing required column(s): {missing}. "
            f"Found columns: {list(df.columns)}"
        )


def load_raw(input_dir: Path):
    orders_path = input_dir / "orders.csv"
    warehouses_path = input_dir / "warehouses.csv"
    transport_path = input_dir / "transport_types.csv"
    wte_path = input_dir / "warehouse_time_estimates.csv"

    for required_path in [orders_path, warehouses_path, transport_path]:
        if not required_path.exists():
            raise FileNotFoundError(f"Required input file not found: {required_path}")

    orders = pd.read_csv(orders_path)
    warehouses = pd.read_csv(warehouses_path)
    transport = pd.read_csv(transport_path)

    check_columns(orders, REQUIRED_ORDER_COLS, "orders.csv")
    check_columns(warehouses, REQUIRED_WAREHOUSE_COLS, "warehouses.csv")
    check_columns(transport, REQUIRED_TRANSPORT_COLS, "transport_types.csv")

    wte = None
    if wte_path.exists():
        wte = pd.read_csv(wte_path)
        check_columns(
            wte,
            ["task_id", "courier_id", "warehouse_id", "estimated_duration_sec"],
            "warehouse_time_estimates.csv",
        )
    else:
        print(f"  (no {wte_path.name} found — enriched_warehouses.csv will skip WTE stats)")

    return orders, warehouses, transport, wte


def enrich_orders(orders: pd.DataFrame, warehouses: pd.DataFrame, transport: pd.DataFrame) -> pd.DataFrame:
    orders = orders.copy()

    # --- Parse timestamps ---
    for col in ["pickup_ready_at", "created_at", "delivery_deadline_at"]:
        orders[col] = pd.to_datetime(orders[col], utc=True)

    # --- Time-derived features (seconds) ---
    orders["time_window_sec"] = (
            orders["delivery_deadline_at"] - orders["pickup_ready_at"]
    ).dt.total_seconds().astype(int)
    orders["lead_time_sec"] = (
            orders["delivery_deadline_at"] - orders["created_at"]
    ).dt.total_seconds().astype(int)
    orders["prep_time_sec"] = (
            orders["pickup_ready_at"] - orders["created_at"]
    ).dt.total_seconds().astype(int)

    orders["pickup_ready_ts"] = orders["pickup_ready_at"].astype(np.int64) // 10**9
    orders["deadline_ts"] = orders["delivery_deadline_at"].astype(np.int64) // 10**9

    # --- Distance from assigned warehouse ---
    wh = warehouses.rename(columns={"lat": "wh_lat", "lon": "wh_lon"})
    orders = orders.merge(wh[["task_id", "warehouse_id", "wh_lat", "wh_lon"]],
                          on=["task_id", "warehouse_id"], how="left")

    missing_wh = orders["wh_lat"].isna().sum()
    if missing_wh:
        print(f"  WARNING: {missing_wh} order(s) reference a (task_id, warehouse_id) "
              f"not found in warehouses.csv — dist_from_warehouse_km will be NaN for these")

    orders["dist_from_warehouse_km"] = orders.apply(
        lambda r: haversine_km(r["wh_lat"], r["wh_lon"], r["order_lat"], r["order_lon"])
        if pd.notna(r["wh_lat"]) else np.nan,
        axis=1,
    )

    # --- Per-transport-type travel time & feasibility ---
    for _, row in transport.iterrows():
        norm = normalize_transport_code(row["code"])
        speed = float(row["approx_speed_kmh"])
        if speed <= 0:
            print(f"  WARNING: transport '{row['code']}' has non-positive speed "
                  f"({speed}); skipping travel-time columns for it")
            continue

        travel_col = f"straight_line_travel_sec_{norm}"
        feasible_col = f"feasible_solo_{norm}"

        orders[travel_col] = (orders["dist_from_warehouse_km"] / speed * 3600)
        orders[travel_col] = orders[travel_col].round().astype("Int64")  # nullable int
        orders[feasible_col] = orders[travel_col] < orders["time_window_sec"]

    orders = orders.drop(columns=["wh_lat", "wh_lon"])
    return orders


def enrich_warehouses(warehouses: pd.DataFrame, wte: pd.DataFrame | None) -> pd.DataFrame:
    if wte is None:
        return warehouses.copy()

    wte_summary = wte.groupby(["task_id", "warehouse_id"])["estimated_duration_sec"].agg(
        wte_mean="mean", wte_min="min", wte_max="max", n_couriers_in_range="count"
    ).reset_index()

    return warehouses.merge(wte_summary, on=["task_id", "warehouse_id"], how="left")


def main():
    parser = argparse.ArgumentParser(
        description="Build enriched datasets from raw clustering-task CSVs."
    )
    parser.add_argument(
        "--input-dir", type=Path, default=Path("."),
        help="Directory containing orders.csv, warehouses.csv, transport_types.csv, "
             "and optionally warehouse_time_estimates.csv (default: current directory)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("."),
        help="Directory to write enriched_orders.csv and enriched_warehouses.csv "
             "(default: current directory)",
    )
    args = parser.parse_args()

    print(f"Reading raw data from: {args.input_dir.resolve()}")
    orders, warehouses, transport, wte = load_raw(args.input_dir)
    print(f"  orders.csv:           {len(orders)} rows")
    print(f"  warehouses.csv:       {len(warehouses)} rows")
    print(f"  transport_types.csv:  {len(transport)} rows")
    if wte is not None:
        print(f"  warehouse_time_estimates.csv: {len(wte)} rows")

    print("\nEnriching orders...")
    enriched_orders = enrich_orders(orders, warehouses, transport)

    print("Enriching warehouses...")
    enriched_warehouses = enrich_warehouses(warehouses, wte)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_orders_path = args.output_dir / "enriched_orders.csv"
    out_warehouses_path = args.output_dir / "enriched_warehouses.csv"

    enriched_orders.to_csv(out_orders_path, index=False)
    enriched_warehouses.to_csv(out_warehouses_path, index=False)

    print(f"\nWrote {out_orders_path} ({enriched_orders.shape[0]} rows, "
          f"{enriched_orders.shape[1]} columns)")
    print(f"Wrote {out_warehouses_path} ({enriched_warehouses.shape[0]} rows, "
          f"{enriched_warehouses.shape[1]} columns)")

    # --- Quick feasibility summary ---
    feasible_cols = [c for c in enriched_orders.columns if c.startswith("feasible_solo_")]
    if feasible_cols:
        print("\nFeasibility summary (solo straight-line delivery):")
        for col in feasible_cols:
            transport_name = col.replace("feasible_solo_", "")
            n_infeasible = (~enriched_orders[col].astype(bool)).sum()
            total = len(enriched_orders)
            pct = 100 * n_infeasible / total if total else 0
            print(f"  {transport_name:10s}: {n_infeasible:5d} / {total} infeasible ({pct:.1f}%)")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)