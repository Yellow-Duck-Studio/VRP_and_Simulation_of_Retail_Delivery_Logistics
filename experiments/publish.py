from __future__ import annotations

import shutil
from pathlib import Path

from submission import build_submission_file


def publish_algorithm_run(
    run_root: Path,
    algorithm_name: str,
    data_dir: Path,
) -> tuple[Path, Path, Path]:
    algorithm_dir = run_root / algorithm_name
    source_json = algorithm_dir / "master_clusterizations.json"
    source_csv = algorithm_dir / "master_clusterizations.csv"

    if not source_json.exists() or not source_csv.exists():
        raise FileNotFoundError(f"Published files not found for algorithm '{algorithm_name}' in {algorithm_dir}")

    target_json = data_dir / "master_clusterizations.json"
    target_csv = data_dir / "master_clusterizations.csv"

    shutil.copyfile(source_json, target_json)
    shutil.copyfile(source_csv, target_csv)

    submission_path = data_dir / "final_submission.csv"
    build_submission_file(
        warehouses_path=data_dir / "warehouses.csv",
        transport_types_path=data_dir / "transport_types.csv",
        orders_path=data_dir / "orders.csv",
        clusterizations_csv_path=target_csv,
        output_path=submission_path,
    )

    return target_json, target_csv, submission_path
