import pandas as pd


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

warehouses_df = pd.read_csv("data/warehouses.csv")
transport_types_df = pd.read_csv("data/transport_types.csv")
orders_df = pd.read_csv("data/orders.csv")
submission_df = pd.read_csv("data/master_clusterizations.csv")

final_submission = make_checker_submission(
    warehouses_df,
    transport_types_df,
    orders_df,
    submission_df,
)

final_submission.to_csv("data/final_submission.csv", index=False)
