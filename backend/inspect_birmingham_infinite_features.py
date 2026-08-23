from pathlib import Path

import numpy as np
import pandas as pd


TARGET_COLUMN = "target_occupancy_rate_30m"

BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent

TRAIN_FILE = (
    PROJECT_ROOT
    / "datasets"
    / "processed"
    / "birmingham"
    / TARGET_COLUMN
    / "train.parquet"
)

VALIDATION_FILE = (
    PROJECT_ROOT
    / "datasets"
    / "processed"
    / "birmingham"
    / TARGET_COLUMN
    / "validation.parquet"
)


METADATA_COLUMNS = {
    "source_facility_code",
    "normalized_at",
    "observation_present",
    "gap_status",
    "is_operational_gap",
    "is_data_gap",
    "sequence_break",
    "is_eligible_for_sequence",
    "quality_status",
    "quality_flags",
    "source",
    "target_exclusion_reason",
}


TARGET_COLUMNS = {
    "target_occupancy_rate_30m",
    "target_occupancy_rate_1h",
    "target_occupancy_rate_2h",
    "target_tomorrow_morning_demand",
}


TARGET_AVAILABILITY_COLUMNS = {
    "target_30m_available",
    "target_1h_available",
    "target_2h_available",
    "target_tomorrow_morning_available",
}


def identify_features(df: pd.DataFrame) -> list[str]:

    excluded = (
        METADATA_COLUMNS
        | TARGET_COLUMNS
        | TARGET_AVAILABILITY_COLUMNS
    )

    return [
        column
        for column in df.columns
        if column not in excluded
    ]


def inspect_dataset(
    df: pd.DataFrame,
    dataset_name: str,
) -> None:

    print()
    print("=" * 78)
    print(f"{dataset_name.upper()} INFINITE-VALUE INSPECTION")
    print("=" * 78)

    features = identify_features(df)

    print()
    print(f"Rows              : {len(df):,}")
    print(f"Features          : {len(features):,}")

    numeric_features = [
        column
        for column in features
        if pd.api.types.is_numeric_dtype(
            df[column]
        )
    ]

    print(
        f"Numeric features  : {len(numeric_features):,}"
    )

    print()
    print("--- INFINITE VALUES BY FEATURE ---")

    records = []

    for column in numeric_features:

        values = pd.to_numeric(
            df[column],
            errors="coerce",
        )

        positive_inf = int(
            np.isposinf(
                values.to_numpy(
                    dtype=float
                )
            ).sum()
        )

        negative_inf = int(
            np.isneginf(
                values.to_numpy(
                    dtype=float
                )
            ).sum()
        )

        total_inf = (
            positive_inf
            + negative_inf
        )

        if total_inf > 0:

            records.append(
                {
                    "feature": column,
                    "positive_infinity": positive_inf,
                    "negative_infinity": negative_inf,
                    "total_infinity": total_inf,
                }
            )

    if not records:

        print(
            "NO INFINITE NUMERIC VALUES FOUND"
        )

        return

    result = (
        pd.DataFrame(records)
        .sort_values(
            "total_infinity",
            ascending=False,
        )
    )

    print(
        result.to_string(
            index=False
        )
    )

    print()
    print(
        f"Features containing infinity : {len(result):,}"
    )

    print(
        f"Total infinite cells          : "
        f"{int(result['total_infinity'].sum()):,}"
    )

    # --------------------------------------------------------------
    # Show sample rows for every offending feature.
    # --------------------------------------------------------------

    print()
    print("--- SAMPLE INFINITE OBSERVATIONS ---")

    for _, row in result.iterrows():

        feature = row["feature"]

        mask = np.isinf(
            pd.to_numeric(
                df[feature],
                errors="coerce",
            ).to_numpy(
                dtype=float
            )
        )

        sample = df.loc[
            mask,
            [
                "source_facility_code",
                "normalized_at",
                feature,
            ],
        ].head(10)

        print()
        print(
            f"FEATURE: {feature}"
        )

        print(
            sample.to_string(
                index=False
            )
        )


def main() -> int:

    print("=" * 78)
    print(
        "SMARTPARK AI - BIRMINGHAM INFINITE VALUE DIAGNOSTIC"
    )
    print("=" * 78)

    print()
    print(
        "IMPORTANT:"
    )
    print(
        "This script ONLY inspects the persisted datasets."
    )
    print(
        "It does NOT modify train.parquet."
    )
    print(
        "It does NOT modify validation.parquet."
    )
    print(
        "It does NOT modify test.parquet."
    )

    if not TRAIN_FILE.exists():

        print()
        print(
            f"Training file not found: {TRAIN_FILE}"
        )

        return 1

    if not VALIDATION_FILE.exists():

        print()
        print(
            f"Validation file not found: "
            f"{VALIDATION_FILE}"
        )

        return 1

    print()
    print(
        f"Training file:"
    )

    print(
        f"  {TRAIN_FILE}"
    )

    print()
    print(
        f"Validation file:"
    )

    print(
        f"  {VALIDATION_FILE}"
    )

    print()
    print(
        "Loading training dataset..."
    )

    train_df = pd.read_parquet(
        TRAIN_FILE
    )

    print(
        "Loading validation dataset..."
    )

    validation_df = pd.read_parquet(
        VALIDATION_FILE
    )

    inspect_dataset(
        train_df,
        "training",
    )

    inspect_dataset(
        validation_df,
        "validation",
    )

    print()
    print("=" * 78)
    print(
        "INFINITE VALUE DIAGNOSTIC COMPLETED"
    )
    print("=" * 78)

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )