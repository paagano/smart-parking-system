"""
SmartPark AI
Birmingham Training Dataset - End-to-End Verification

Purpose
-------
Build the complete Birmingham feature pipeline and then construct
target-specific chronological training datasets.

This script is intentionally a verification runner.
It does NOT modify the existing feature pipeline or training
dataset builder.
"""

from __future__ import annotations

from app.ml.features.feature_pipeline import (
    build_birmingham_feature_pipeline,
)

from birmingham_training_dataset import (
    build_birmingham_training_datasets,
    validate_training_dataset,
)


def main() -> int:
    print()
    print("=" * 78)
    print("SMARTPARK AI - BIRMINGHAM TRAINING DATASET VERIFICATION")
    print("=" * 78)

    # ================================================================
    # 1. BUILD FEATURE PIPELINE
    # ================================================================

    print()
    print("--- 1. BUILDING BIRMINGHAM FEATURE PIPELINE ---")

    pipeline_result = build_birmingham_feature_pipeline()

    print(
        f"Feature pipeline rows:    "
        f"{len(pipeline_result.dataframe):,}"
    )

    print(
        f"Feature pipeline columns: "
        f"{len(pipeline_result.dataframe.columns):,}"
    )

    print(
        f"ML features:              "
        f"{len(pipeline_result.feature_columns):,}"
    )

    print(
        f"Targets:                  "
        f"{len(pipeline_result.target_columns):,}"
    )

    print(
        f"Target availability:      "
        f"{len(pipeline_result.target_availability_columns):,}"
    )

    # ================================================================
    # 2. BUILD TRAINING DATASETS
    # ================================================================

    print()
    print("--- 2. BUILDING TARGET-SPECIFIC TRAINING DATASETS ---")

    result = build_birmingham_training_datasets(
        feature_dataframe=pipeline_result.dataframe,
        feature_columns=pipeline_result.feature_columns,
        metadata_columns=pipeline_result.metadata_columns,
    )

    # ================================================================
    # 3. BASIC SOURCE PROFILE
    # ================================================================

    print()
    print("--- 3. SOURCE DATASET ---")

    print(
        f"Source rows:              "
        f"{len(result.source_dataframe):,}"
    )

    print(
        f"Facilities:               "
        f"{result.statistics['facility_count']}"
    )

    print(
        f"Features:                 "
        f"{len(result.feature_columns)}"
    )

    print(
        f"Targets:                  "
        f"{len(result.target_columns)}"
    )

    print(
        f"Target datasets:          "
        f"{len(result.target_datasets)}"
    )

    # ================================================================
    # 4. TARGET DATASET PROFILE
    # ================================================================

    print()
    print("--- 4. TARGET-SPECIFIC DATASETS ---")

    for target, split_result in result.target_datasets.items():

        stats = split_result.statistics

        print()
        print(target)
        print("-" * 70)

        print(
            f"Source rows:              "
            f"{stats['source_rows']:,}"
        )

        print(
            f"Eligible rows:            "
            f"{stats['eligible_rows']:,}"
            f" ({stats['eligible_pct']:.2f}%)"
        )

        print(
            f"Excluded rows:            "
            f"{stats['excluded_rows']:,}"
        )

        print(
            f"Train:                    "
            f"{stats['train_rows']:,}"
            f" ({stats['train_pct']:.2f}%)"
        )

        print(
            f"Validation:               "
            f"{stats['validation_rows']:,}"
            f" ({stats['validation_pct']:.2f}%)"
        )

        print(
            f"Test:                     "
            f"{stats['test_rows']:,}"
            f" ({stats['test_pct']:.2f}%)"
        )

        print(
            f"Target minimum:           "
            f"{stats['minimum']}"
        )

        print(
            f"Target maximum:           "
            f"{stats['maximum']}"
        )

        print(
            f"Target mean:              "
            f"{stats['mean']}"
        )

        print(
            f"Train end:                "
            f"{stats['train_end']}"
        )

        print(
            f"Validation end:           "
            f"{stats['validation_end']}"
        )

        print(
            f"Test end:                 "
            f"{stats['test_end']}"
        )

    # ================================================================
    # 5. COMMON TARGET SUBSET
    # ================================================================

    print()
    print("--- 5. COMMON TARGET SUBSET ---")

    print(
        "Rows with all four targets: "
        f"{result.statistics['rows_with_all_targets_available']:,}"
    )

    print(
        "Percentage of source:       "
        f"{result.statistics['all_target_availability_pct']:.2f}%"
    )

    # ================================================================
    # 6. LEAKAGE CONTRACT
    # ================================================================

    print()
    print("--- 6. LEAKAGE CONTRACT ---")

    leakage_flags = {
        "future_data_used":
            result.metadata.get("future_data_used", False),

        "target_data_used_as_feature":
            result.metadata.get(
                "target_data_used_as_feature",
                False,
            ),

        "cross_facility_data_used":
            result.metadata.get(
                "cross_facility_data_used",
                False,
            ),

        "forward_lookup_used":
            result.metadata.get(
                "forward_lookup_used",
                False,
            ),

        "centered_windows_used":
            result.metadata.get(
                "centered_windows_used",
                False,
            ),

        "random_shuffle":
            result.metadata.get(
                "random_shuffle",
                False,
            ),

        "target_imputation":
            result.metadata.get(
                "target_imputation",
                False,
            ),

        "chronological_split":
            result.metadata.get(
                "chronological_split",
                False,
            ),
    }

    for name, value in leakage_flags.items():
        print(
            f"{name:<35}: {value}"
        )

    # ================================================================
    # 7. VALIDATION
    # ================================================================

    print()
    print("--- 7. TRAINING DATASET VALIDATION ---")

    validation = validate_training_dataset(result)

    print(
        f"Valid:                    "
        f"{validation['valid']}"
    )

    print(
        f"Errors:                   "
        f"{validation['errors']}"
    )

    print(
        f"Warnings:                 "
        f"{validation['warnings']}"
    )

    # ================================================================
    # 8. EXPECTED COUNTS FROM TARGET AUDIT
    # ================================================================

    print()
    print("--- 8. TARGET AUDIT CROSS-CHECK ---")

    expected_counts = {
        "target_occupancy_rate_30m": 33_206,
        "target_occupancy_rate_1h": 31_280,
        "target_occupancy_rate_2h": 27_384,
        "target_tomorrow_morning_demand": 33_313,
    }

    count_checks_passed = True

    for target, expected in expected_counts.items():

        actual = result.target_datasets[
            target
        ].statistics["eligible_rows"]

        passed = actual == expected

        if not passed:
            count_checks_passed = False

        print(
            f"{target:<40} "
            f"Expected={expected:,} "
            f"Actual={actual:,} "
            f"PASS={passed}"
        )

    # ================================================================
    # 9. STRUCTURAL ASSERTIONS
    # ================================================================

    print()
    print("--- 9. STRUCTURAL ASSERTIONS ---")

    assertions = []

    # Source row preservation
    assertions.append(
        (
            "Source row count preserved",
            len(result.source_dataframe)
            == len(pipeline_result.dataframe),
        )
    )

    # Four target datasets
    assertions.append(
        (
            "Four target datasets created",
            len(result.target_datasets) == 4,
        )
    )

    # Features
    assertions.append(
        (
            "Feature columns preserved",
            len(result.feature_columns)
            == len(pipeline_result.feature_columns),
        )
    )

    # No future data
    assertions.append(
        (
            "Future data not used",
            result.metadata["future_data_used"] is False,
        )
    )

    # No target-as-feature leakage
    assertions.append(
        (
            "Targets not used as features",
            result.metadata[
                "target_data_used_as_feature"
            ] is False,
        )
    )

    # No cross-facility leakage
    assertions.append(
        (
            "Cross-facility data not used",
            result.metadata[
                "cross_facility_data_used"
            ] is False,
        )
    )

    # No forward lookup
    assertions.append(
        (
            "Forward lookup not used",
            result.metadata[
                "forward_lookup_used"
            ] is False,
        )
    )

    # No centered windows
    assertions.append(
        (
            "Centered windows not used",
            result.metadata[
                "centered_windows_used"
            ] is False,
        )
    )

    # Chronological split
    assertions.append(
        (
            "Chronological splitting enabled",
            result.metadata[
                "chronological_split"
            ] is True,
        )
    )

    # No random shuffle
    assertions.append(
        (
            "Random shuffle disabled",
            result.metadata[
                "random_shuffle"
            ] is False,
        )
    )

    # No target imputation
    assertions.append(
        (
            "Target imputation disabled",
            result.metadata[
                "target_imputation"
            ] is False,
        )
    )

    for name, passed in assertions:
        print(
            f"{name:<45}: "
            f"{'PASS' if passed else 'FAIL'}"
        )

    assertions_passed = all(
        passed
        for _, passed in assertions
    )

    # ================================================================
    # 10. FINAL RESULT
    # ================================================================

    print()
    print("=" * 78)

    if (
        validation["valid"]
        and count_checks_passed
        and assertions_passed
    ):
        print(
            "BIRMINGHAM TRAINING DATASET VERIFICATION PASSED"
        )
        print("=" * 78)
        print()

        print(
            "The Birmingham feature pipeline output has been "
            "successfully transformed into target-specific "
            "chronological training datasets."
        )

        print()
        print(
            "Next step: persist the datasets and then begin "
            "baseline model training."
        )

        return 0

    print(
        "BIRMINGHAM TRAINING DATASET VERIFICATION FAILED"
    )
    print("=" * 78)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())