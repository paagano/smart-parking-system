import pandas as pd

from app.ml.features.feature_pipeline import (
    build_feature_pipeline,
    validate_feature_pipeline,
)


print()
print('=' * 70)
print('SMARTPARK AI FEATURE PIPELINE - SANITY TEST')
print('=' * 70)


# ============================================================
# Synthetic ML input
# ============================================================

df = pd.DataFrame({
    'source_facility_code': ['TEST'],
    'normalized_at': pd.to_datetime(['2024-01-02 08:00:00']),

    'observation_present': [True],
    'gap_status': ['CONTINUOUS'],
    'is_operational_gap': [False],
    'is_data_gap': [False],
    'sequence_break': [False],
    'is_eligible_for_sequence': [True],
    'quality_status': ['CLEAN'],
    'quality_flags': [[]],
    'source': ['TEST'],

    'total_spaces': [100],
    'occupied_spaces': [50],
    'available_spaces': [50],
    'occupancy_rate': [0.50],

    'target_occupancy_rate_30m': [0.55],
    'target_occupancy_rate_1h': [0.60],
    'target_occupancy_rate_2h': [0.65],
    'target_tomorrow_morning_demand': [0.45],

    'target_30m_available': [True],
    'target_1h_available': [True],
    'target_2h_available': [True],
    'target_tomorrow_morning_available': [True],

    'target_exclusion_reason': ['NONE'],
})


print()
print('--- INPUT ---')
print('Rows:', len(df))
print('Columns:', len(df.columns))


# ============================================================
# Build pipeline
# ============================================================

result = build_feature_pipeline(df)


print()
print('--- RESULT ---')
print('Rows:', len(result.dataframe))
print('Columns:', len(result.dataframe.columns))
print('Features:', len(result.feature_columns))
print('Targets:', len(result.target_columns))
print('Target availability:', len(result.target_availability_columns))
print('Metadata:', len(result.metadata_columns))


# ============================================================
# Row preservation
# ============================================================

print()
print('--- ROW PRESERVATION ---')

print('Input rows:', len(df))
print('Output rows:', len(result.dataframe))
print('Row count preserved:', len(df) == len(result.dataframe))
print('Index preserved:', df.index.equals(result.dataframe.index))


# ============================================================
# Leakage
# ============================================================

print()
print('--- LEAKAGE CONTRACT ---')

print('Future data:', result.metadata['future_data_used'])
print('Target data:', result.metadata['target_data_used'])
print('Cross-facility:', result.metadata['cross_facility_data_used'])
print('Forward lookup:', result.metadata['forward_lookup_used'])
print('Centered windows:', result.metadata['centered_windows_used'])


# ============================================================
# Feature groups
# ============================================================

print()
print('--- FEATURE GROUPS ---')

for name, columns in result.metadata['feature_groups'].items():
    print(f'{name:12}: {len(columns)}')


# ============================================================
# Targets
# ============================================================

print()
print('--- TARGET COLUMNS ---')

for column in result.target_columns:
    print(' ', column)

print()
print('--- TARGET AVAILABILITY ---')

for column in result.target_availability_columns:
    print(' ', column)


# ============================================================
# Structural checks
# ============================================================

print()
print('--- STRUCTURAL CHECKS ---')

feature_set = set(result.feature_columns)
target_set = set(result.target_columns)
metadata_set = set(result.metadata_columns)

print(
    'Duplicate feature names:',
    len(result.feature_columns) != len(feature_set)
)

print(
    'Feature/target overlap:',
    sorted(feature_set & target_set)
)

print(
    'Feature/metadata overlap:',
    sorted(feature_set & metadata_set)
)


# ============================================================
# Validation
# ============================================================

print()
print('--- PIPELINE VALIDATION ---')

validation = validate_feature_pipeline(result.dataframe)

print('Valid:', validation['valid'])
print('Errors:', validation['errors'])
print('Warnings:', validation['warnings'])


# ============================================================
# Assertions
# ============================================================

print()
print('--- ASSERTIONS ---')

assert len(result.dataframe) == len(df)

assert df.index.equals(
    result.dataframe.index
)

assert result.metadata['future_data_used'] is False
assert result.metadata['target_data_used'] is False
assert result.metadata['cross_facility_data_used'] is False
assert result.metadata['forward_lookup_used'] is False
assert result.metadata['centered_windows_used'] is False

assert not (feature_set & target_set)
assert not (feature_set & metadata_set)

assert validation['valid'] is True

print('ALL ASSERTIONS PASSED')


print()
print('=' * 70)
print('FEATURE PIPELINE SANITY TEST PASSED')
print('=' * 70)
print()
