import pandas as pd
from pathlib import Path


def make_checker_submission(
    warehouses_df: pd.DataFrame,
    transport_types_df: pd.DataFrame,
    orders_df: pd.DataFrame,
    submission_df: pd.DataFrame,
) -> pd.DataFrame:
    payload = "\n\n".join(
        df.to_csv(index=False).strip()
        for df in [
            warehouses_df,
            transport_types_df,
            orders_df,
            submission_df,
        ]
    )

    return pd.DataFrame({
        "id": [0],
        "payload": [payload],
    })

import pandas as pd

def build_submission_file(
    warehouses_path: str | Path,
    transport_types_path: str | Path,
    orders_path: str | Path,
    clusterizations_csv_path: str | Path,
    output_path: str | Path,
) -> Path:
    warehouses_df = pd.read_csv(warehouses_path)
    transport_types_df = pd.read_csv(transport_types_path)
    orders_df = pd.read_csv(orders_path)
    submission_df = pd.read_csv(clusterizations_csv_path)

    final_submission = make_checker_submission(
        warehouses_df,
        transport_types_df,
        orders_df,
        submission_df,
    )
    output_path = Path(output_path)
    final_submission.to_csv(output_path, index=False)
    return output_path


if __name__ == "__main__":
    build_submission_file(
        warehouses_path="data/small/warehouses.csv",
        transport_types_path="data/transport_types.csv",
        orders_path="data/small/orders.csv",
        clusterizations_csv_path="data/master_clusterizations.csv",
        output_path="data/final_submission.csv",
    )
