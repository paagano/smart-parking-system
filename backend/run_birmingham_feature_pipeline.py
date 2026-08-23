from pathlib import Path

from app.ml.data.dataset_builder import build_birmingham_ml_dataset
from app.ml.features.feature_pipeline import (
    build_feature_pipeline,
    validate_feature_pipeline,
)


# ============================================================
# Configuration
# ============================================================

DATASET_ROOT = "../datasets/raw"


# ============================================================
# Main
# ============================================================

def main() -> None:

    print()
    print("=" * 78)
    print("SMARTPARK AI - BIRMINGHAM FEATURE PIPELINE")
    print("=" * 78)

    # --------------------------------------------------------
    # 1. Build Birmingham ML dataset
    # --------------------------------------------------------

    print()
    print("--- 1. BUILDING BIRMINGHAM ML DATASET ---")

    dataset_result = build_birmingham_ml_dataset(
        dataset_root=DATASET_ROOT,
    )

    source_dataframe = (
        dataset_result.dataframe
    )

    print(
        "Input rows:",
        len(source_dataframe),
    )

    print(
        "Input columns:",
        len(source_dataframe.columns),
    )

    # --------------------------------------------------------
    # 2. Run complete feature pipeline
    # --------------------------------------------------------

    print()
    print("--- 2. RUNNING COMPLETE FEATURE PIPELINE ---")

    result = build_feature_pipeline(
        source_dataframe
    )

    # --------------------------------------------------------
    # 3. Basic result
    # --------------------------------------------------------

    print()
    print("--- 3. PIPELINE RESULT ---")

    print(
        "Output rows:",
        len(result.dataframe),
    )

    print(
        "Output columns:",
        len(result.dataframe.columns),
    )

    print(
        "Feature count:",
        len(result.feature_columns),
    )

    print(
        "Target count:",
        len(result.target_columns),
    )

    print(
        "Target availability count:",
        len(result.target_availability_columns),
    )

    print(
        "Metadata count:",
        len(result.metadata_columns),
    )

    # --------------------------------------------------------
    # 4. Row preservation
    # --------------------------------------------------------

    print()
    print("--- 4. ROW PRESERVATION ---")

    rows_preserved = (
        len(source_dataframe)
        == len(result.dataframe)
    )

    index_preserved = (
        source_dataframe.index.equals(
            result.dataframe.index
        )
    )

    print(
        "Rows preserved:",
        rows_preserved,
    )

    print(
        "Index preserved:",
        index_preserved,
    )

    # --------------------------------------------------------
    # 5. Feature groups
    # --------------------------------------------------------

    print()
    print("--- 5. FEATURE GROUPS ---")

    feature_groups = result.metadata[
        "feature_groups"
    ]

    for name, columns in feature_groups.items():

        print(
            f"{name:15}: {len(columns)}"
        )

    # --------------------------------------------------------
    # 6. Leakage contract
    # --------------------------------------------------------

    print()
    print("--- 6. LEAKAGE CONTRACT ---")

    leakage_fields = (
        "future_data_used",
        "target_data_used",
        "cross_facility_data_used",
        "forward_lookup_used",
        "centered_windows_used",
    )

    for field in leakage_fields:

        print(
            f"{field:30}: "
            f"{result.metadata[field]}"
        )

    # --------------------------------------------------------
    # 7. Feature duplicate check
    # --------------------------------------------------------

    print()
    print("--- 7. FEATURE STRUCTURE ---")

    feature_columns = (
        result.feature_columns
    )

    duplicate_features = [
        column
        for column in dict.fromkeys(
            feature_columns
        )
        if feature_columns.count(
            column
        ) > 1
    ]

    print(
        "Duplicate feature columns:",
        len(duplicate_features),
    )

    if duplicate_features:

        print(
            "Duplicates:",
            duplicate_features,
        )

    # --------------------------------------------------------
    # 8. Missing feature columns
    # --------------------------------------------------------

    missing_features = [
        column
        for column in result.feature_columns
        if column not in result.dataframe.columns
    ]

    print(
        "Missing feature columns:",
        len(missing_features),
    )

    if missing_features:

        print(
            "Missing:",
            missing_features,
        )

    # --------------------------------------------------------
    # 9. Feature/target overlap
    # --------------------------------------------------------

    feature_set = set(
        result.feature_columns
    )

    target_set = set(
        result.target_columns
    )

    overlap = sorted(
        feature_set & target_set
    )

    print(
        "Feature/target overlap:",
        len(overlap),
    )

    if overlap:

        print(
            "Overlap:",
            overlap,
        )

    # --------------------------------------------------------
    # 10. Missing values
    # --------------------------------------------------------

    print()
    print("--- 8. MISSING VALUE PROFILE ---")

    feature_nulls = (
        result.dataframe[
            list(result.feature_columns)
        ]
        .isna()
        .sum()
    )

    total_feature_nulls = int(
        feature_nulls.sum()
    )

    columns_with_nulls = (
        feature_nulls[
            feature_nulls > 0
        ]
        .sort_values(
            ascending=False
        )
    )

    print(
        "Total feature null cells:",
        total_feature_nulls,
    )

    print(
        "Features containing nulls:",
        len(columns_with_nulls),
    )

    if not columns_with_nulls.empty:

        print()
        print(
            "Top 20 features by null count:"
        )

        print(
            columns_with_nulls
            .head(20)
            .to_string()
        )

    # --------------------------------------------------------
    # 11. Infinite values
    # --------------------------------------------------------

    print()
    print("--- 9. INFINITE VALUE PROFILE ---")

    numeric_features = (
        result.dataframe[
            list(result.feature_columns)
        ]
        .select_dtypes(
            include="number"
        )
    )

    infinite_cells = 0

    if not numeric_features.empty:

        infinite_cells = int(
            numeric_features
            .isin(
                [float("inf"), float("-inf")]
            )
            .sum()
            .sum()
        )

    print(
        "Infinite numeric cells:",
        infinite_cells,
    )

    # --------------------------------------------------------
    # 12. Feature dtypes
    # --------------------------------------------------------

    print()
    print("--- 10. FEATURE DTYPES ---")

    dtype_counts = (
        result.dataframe[
            list(result.feature_columns)
        ]
        .dtypes
        .astype(str)
        .value_counts()
    )

    print(
        dtype_counts.to_string()
    )

    # --------------------------------------------------------
    # 13. Target profile
    # --------------------------------------------------------

    print()
    print("--- 11. TARGET PROFILE ---")

    for column in result.target_columns:

        series = (
            result.dataframe[column]
        )

        print()
        print(column)

        print(
            "  Non-null:",
            int(series.notna().sum()),
        )

        print(
            "  Null:",
            int(series.isna().sum()),
        )

        if series.notna().any():

            print(
                "  Min:",
                series.min(),
            )

            print(
                "  Max:",
                series.max(),
            )

            print(
                "  Mean:",
                series.mean(),
            )

    # --------------------------------------------------------
    # 14. Target availability
    # --------------------------------------------------------

    print()
    print("--- 12. TARGET AVAILABILITY ---")

    for column in (
        result.target_availability_columns
    ):

        series = (
            result.dataframe[column]
        )

        true_count = int(
            series.fillna(False)
            .astype(bool)
            .sum()
        )

        false_count = (
            len(series)
            - true_count
        )

        print(
            f"{column:40}: "
            f"available={true_count:,} "
            f"unavailable={false_count:,}"
        )

    # --------------------------------------------------------
    # 15. Pipeline validation
    # --------------------------------------------------------

    print()
    print("--- 13. PIPELINE VALIDATION ---")

    validation = (
        validate_feature_pipeline(
            result.dataframe
        )
    )

    print(
        "Valid:",
        validation["valid"],
    )

    print(
        "Errors:",
        validation["errors"],
    )

    print(
        "Warnings:",
        validation["warnings"],
    )

    # --------------------------------------------------------
    # 16. Final assertions
    # --------------------------------------------------------

    print()
    print("--- 14. FINAL ASSERTIONS ---")

    assert rows_preserved, (
        "Pipeline changed row count."
    )

    assert index_preserved, (
        "Pipeline changed dataframe index/order."
    )

    assert not duplicate_features, (
        "Duplicate feature columns detected."
    )

    assert not missing_features, (
        "Feature columns missing from output."
    )

    assert not overlap, (
        "Feature/target overlap detected."
    )

    assert (
        result.metadata[
            "future_data_used"
        ] is False
    )

    assert (
        result.metadata[
            "target_data_used"
        ] is False
    )

    assert (
        result.metadata[
            "cross_facility_data_used"
        ] is False
    )

    assert (
        result.metadata[
            "forward_lookup_used"
        ] is False
    )

    assert (
        result.metadata[
            "centered_windows_used"
        ] is False
    )

    assert validation["valid"] is True

    print(
        "ALL FINAL ASSERTIONS PASSED"
    )

    # --------------------------------------------------------
    # 17. Final summary
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print("BIRMINGHAM FEATURE PIPELINE COMPLETED SUCCESSFULLY")
    print("=" * 78)

    print()
    print(
        f"Rows:              {len(result.dataframe):,}"
    )

    print(
        f"Columns:           {len(result.dataframe.columns):,}"
    )

    print(
        f"ML Features:       {len(result.feature_columns):,}"
    )

    print(
        f"Targets:           {len(result.target_columns):,}"
    )

    print(
        f"Target Availability:{len(result.target_availability_columns):,}"
    )

    print(
        f"Metadata:          {len(result.metadata_columns):,}"
    )

    print()
    print("Pipeline validation: PASS")
    print("Leakage validation:   PASS")
    print("Row preservation:     PASS")
    print("Feature structure:    PASS")
    print()


if __name__ == "__main__":
    main()