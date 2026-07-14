from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd


TRANSPORT_ALIAS = {
    "moped": "bike",
    "walking": "foot",
}


def _build_transport_with_fees(transport_csv: Path, couriers_csv: Path) -> pd.DataFrame:
    transport_df = pd.read_csv(transport_csv)
    couriers_df = pd.read_csv(couriers_csv)

    transport_column = "transport_type_normalized" if "transport_type_normalized" in couriers_df.columns else "transport_type"
    grouped = (
        couriers_df.groupby(transport_column, dropna=False)[["per_km_fee", "per_order_fee"]]
        .mean()
        .reset_index()
    )

    fee_by_code: dict[str, dict[str, float]] = {}
    for row in grouped.itertuples():
        raw_name = str(getattr(row, transport_column))
        code = TRANSPORT_ALIAS.get(raw_name, raw_name)
        fee_by_code[code] = {
            "per_km_fee": float(row.per_km_fee),
            "per_order_fee": float(row.per_order_fee),
        }

    transport_df["fixed_fee"] = 0.0
    transport_df["per_km_fee"] = transport_df["code"].map(lambda code: fee_by_code.get(str(code), {}).get("per_km_fee", 0.0))
    transport_df["per_order_fee"] = transport_df["code"].map(lambda code: fee_by_code.get(str(code), {}).get("per_order_fee", 0.0))
    transport_df["per_kg_min_fee"] = 0.0
    return transport_df


def materialize_dataset(
    orders_csv: Path,
    warehouses_csv: Path,
    transport_csv: Path,
    couriers_csv: Path,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(orders_csv, output_dir / "orders.csv")
    shutil.copyfile(warehouses_csv, output_dir / "warehouses.csv")
    shutil.copyfile(couriers_csv, output_dir / "couriers.csv")

    transport_with_fees = _build_transport_with_fees(transport_csv, couriers_csv)
    transport_with_fees.to_csv(output_dir / "transport_types.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a runtime-ready dataset directory for enriched CSV files.")
    parser.add_argument("--orders", required=True)
    parser.add_argument("--warehouses", required=True)
    parser.add_argument("--transport", required=True)
    parser.add_argument("--couriers", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    materialize_dataset(
        orders_csv=Path(args.orders),
        warehouses_csv=Path(args.warehouses),
        transport_csv=Path(args.transport),
        couriers_csv=Path(args.couriers),
        output_dir=Path(args.out_dir),
    )
    print(f"Runtime dataset created in {args.out_dir}")


if __name__ == "__main__":
    main()
