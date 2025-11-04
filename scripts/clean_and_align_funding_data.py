"""
Clean and Align Funding Rate Data

Fixes data quality issues in historical funding rate datasets:
1. Aligns timestamps between Extended and Lighter
2. Forward-fills missing data points
3. Creates clean, synchronized datasets for backtesting

Usage:
    python scripts/clean_and_align_funding_data.py

Output:
    - app/data/cache/funding/clean/extended_historical_31d_cleaned.parquet
    - app/data/cache/funding/clean/lighter_historical_31d_cleaned.parquet
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def load_data():
    """Load raw funding rate data."""
    data_dir = project_root / 'app' / 'data' / 'cache' / 'funding' / 'raw'

    extended_df = pd.read_parquet(data_dir / 'extended_historical_31d.parquet')
    lighter_df = pd.read_parquet(data_dir / 'lighter_historical_31d.parquet')

    # Round Extended timestamps to nearest hour (they're off by 1 second)
    # Extended: 1759618801 (19:00:01) → 1759618800 (19:00:00)
    extended_df['timestamp'] = (extended_df['timestamp'] / 3600).round() * 3600
    extended_df['timestamp'] = extended_df['timestamp'].astype(int)

    print("="*80)
    print("LOADED RAW DATA")
    print("="*80)
    print(f"Extended: {len(extended_df)} records (timestamps rounded to hour)")
    print(f"Lighter:  {len(lighter_df)} records")
    print()

    return extended_df, lighter_df


def analyze_completeness(extended_df, lighter_df):
    """Analyze data completeness per token."""
    tokens = sorted(set(extended_df['base'].unique()) | set(lighter_df['base'].unique()))

    print("="*80)
    print("DATA COMPLETENESS BY TOKEN")
    print("="*80)
    print(f"{'Token':<10} {'Extended':>10} {'Lighter':>10} {'Common TS':>12} {'Overlap %':>10}")
    print("-"*80)

    completeness_report = []

    for token in tokens:
        ext_data = extended_df[extended_df['base'] == token]
        lit_data = lighter_df[lighter_df['base'] == token]

        ext_timestamps = set(ext_data['timestamp'].unique())
        lit_timestamps = set(lit_data['timestamp'].unique())

        common = len(ext_timestamps & lit_timestamps)
        total_unique = len(ext_timestamps | lit_timestamps)
        overlap_pct = (common / total_unique * 100) if total_unique > 0 else 0

        print(f"{token:<10} {len(ext_data):>10} {len(lit_data):>10} {common:>12} {overlap_pct:>9.1f}%")

        completeness_report.append({
            'token': token,
            'extended_records': len(ext_data),
            'lighter_records': len(lit_data),
            'common_timestamps': common,
            'overlap_pct': overlap_pct
        })

    print()
    return completeness_report


def create_unified_timestamp_grid(extended_df, lighter_df):
    """Create a unified timestamp grid covering the common period."""

    # Get overall time range (intersection)
    ext_start = extended_df['timestamp'].min()
    ext_end = extended_df['timestamp'].max()
    lit_start = lighter_df['timestamp'].min()
    lit_end = lighter_df['timestamp'].max()

    # Use the overlapping period
    grid_start = max(ext_start, lit_start)
    grid_end = min(ext_end, lit_end)

    print("="*80)
    print("CREATING UNIFIED TIMESTAMP GRID")
    print("="*80)
    print(f"Extended range: {datetime.fromtimestamp(ext_start)} to {datetime.fromtimestamp(ext_end)}")
    print(f"Lighter range:  {datetime.fromtimestamp(lit_start)} to {datetime.fromtimestamp(lit_end)}")
    print()
    print(f"Unified range:  {datetime.fromtimestamp(grid_start)} to {datetime.fromtimestamp(grid_end)}")
    print(f"Duration:       {(grid_end - grid_start) / 3600 / 24:.1f} days")
    print()

    # Create hourly grid
    timestamps = pd.date_range(
        start=pd.to_datetime(grid_start, unit='s'),
        end=pd.to_datetime(grid_end, unit='s'),
        freq='1H'
    )

    timestamp_grid = [int(ts.timestamp()) for ts in timestamps]

    print(f"Generated {len(timestamp_grid)} hourly timestamps")
    print()

    return timestamp_grid, grid_start, grid_end


def align_and_fill_data(df, timestamp_grid, exchange_name):
    """Align data to unified grid and forward-fill missing values."""

    tokens = df['base'].unique()
    aligned_records = []

    print(f"Aligning {exchange_name} data...")

    for token in tokens:
        token_data = df[df['base'] == token].copy()
        token_data = token_data.sort_values('timestamp')

        # Create complete dataframe with all timestamps
        complete_df = pd.DataFrame({'timestamp': timestamp_grid})

        # Merge with actual data
        complete_df = complete_df.merge(
            token_data[['timestamp', 'funding_rate']],
            on='timestamp',
            how='left'
        )

        # Forward fill missing funding rates (max 6 hours)
        complete_df['funding_rate'] = complete_df['funding_rate'].fillna(method='ffill', limit=6)

        # Backward fill remaining (for start of series)
        complete_df['funding_rate'] = complete_df['funding_rate'].fillna(method='bfill', limit=6)

        # Add metadata
        complete_df['exchange'] = exchange_name
        complete_df['base'] = token
        complete_df['quote'] = 'USD'

        # Track which records were filled
        complete_df['filled'] = complete_df['funding_rate'].isna()

        # Drop any remaining NaN (beyond fill limits)
        before_drop = len(complete_df)
        complete_df = complete_df.dropna(subset=['funding_rate'])
        dropped = before_drop - len(complete_df)

        aligned_records.append(complete_df)

        filled_count = complete_df['filled'].sum()
        print(f"  {token}: {len(complete_df)} records ({filled_count} filled, {dropped} dropped)")

    result_df = pd.concat(aligned_records, ignore_index=True)

    # Drop the 'filled' column
    result_df = result_df.drop(columns=['filled'])

    return result_df


def save_cleaned_data(extended_clean, lighter_clean):
    """Save cleaned datasets."""

    output_dir = project_root / 'app' / 'data' / 'cache' / 'funding' / 'clean'
    output_dir.mkdir(parents=True, exist_ok=True)

    extended_path = output_dir / 'extended_historical_31d_cleaned.parquet'
    lighter_path = output_dir / 'lighter_historical_31d_cleaned.parquet'

    extended_clean.to_parquet(extended_path, index=False)
    lighter_clean.to_parquet(lighter_path, index=False)

    print()
    print("="*80)
    print("SAVED CLEANED DATA")
    print("="*80)
    print(f"Extended: {extended_path}")
    print(f"  Records: {len(extended_clean)}")
    print(f"  Size: {extended_path.stat().st_size / 1024:.1f} KB")
    print()
    print(f"Lighter: {lighter_path}")
    print(f"  Records: {len(lighter_clean)}")
    print(f"  Size: {lighter_path.stat().st_size / 1024:.1f} KB")
    print()


def verify_alignment(extended_clean, lighter_clean):
    """Verify that cleaned datasets are properly aligned."""

    print("="*80)
    print("VERIFICATION")
    print("="*80)

    tokens = sorted(set(extended_clean['base'].unique()) & set(lighter_clean['base'].unique()))

    print(f"{'Token':<10} {'Extended':>10} {'Lighter':>10} {'Match':>10}")
    print("-"*80)

    all_aligned = True

    for token in tokens:
        ext_ts = set(extended_clean[extended_clean['base'] == token]['timestamp'].unique())
        lit_ts = set(lighter_clean[lighter_clean['base'] == token]['timestamp'].unique())

        match = ext_ts == lit_ts
        match_str = "✅ YES" if match else "❌ NO"

        print(f"{token:<10} {len(ext_ts):>10} {len(lit_ts):>10} {match_str:>10}")

        if not match:
            all_aligned = False

    print()

    if all_aligned:
        print("✅ SUCCESS: All tokens have perfectly aligned timestamps!")
    else:
        print("⚠️  WARNING: Some tokens still have misaligned timestamps")

    print()

    # Check for any remaining NaN values
    ext_nan = extended_clean['funding_rate'].isna().sum()
    lit_nan = lighter_clean['funding_rate'].isna().sum()

    if ext_nan > 0 or lit_nan > 0:
        print(f"⚠️  WARNING: Found NaN values - Extended: {ext_nan}, Lighter: {lit_nan}")
    else:
        print("✅ No NaN values in cleaned data")

    return all_aligned


def main():
    """Main execution."""

    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "FUNDING DATA CLEANING & ALIGNMENT" + " " * 25 + "║")
    print("╚" + "═" * 78 + "╝")
    print()

    # Load data
    extended_df, lighter_df = load_data()

    # Analyze completeness
    completeness = analyze_completeness(extended_df, lighter_df)

    # Create unified timestamp grid
    timestamp_grid, grid_start, grid_end = create_unified_timestamp_grid(
        extended_df, lighter_df
    )

    # Align and fill data
    print("="*80)
    print("ALIGNING DATA TO UNIFIED GRID")
    print("="*80)
    print()

    extended_clean = align_and_fill_data(extended_df, timestamp_grid, 'extended')
    print()
    lighter_clean = align_and_fill_data(lighter_df, timestamp_grid, 'lighter')
    print()

    # Save cleaned data
    save_cleaned_data(extended_clean, lighter_clean)

    # Verify alignment
    aligned = verify_alignment(extended_clean, lighter_clean)

    print("="*80)
    print("CLEANING COMPLETE")
    print("="*80)
    print()
    print("Next steps:")
    print("1. Review cleaned data in app/data/cache/funding/clean/")
    print("2. Update backtesting plan to use cleaned datasets")
    print("3. Proceed with backtesting implementation")
    print()

    return aligned


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
