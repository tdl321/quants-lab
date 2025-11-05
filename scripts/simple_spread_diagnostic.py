"""
Simple Spread Diagnostic - Analyze Raw Funding Data

Directly reads funding data parquet files and calculates spreads
to understand what opportunities exist vs what strategy trades.

Usage:
    python scripts/simple_spread_diagnostic.py
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Paths
project_root = Path(__file__).parent.parent
funding_data_path = project_root / "app/data/cache/funding/clean"

print()
print("="*80)
print("SIMPLE SPREAD DIAGNOSTIC")
print("="*80)
print()

# Period
start = int(datetime(2025, 10, 4, 20, 0, 0).timestamp())
end = int(datetime(2025, 10, 11, 23, 59, 59).timestamp())  # 1 week

print(f"Period: {datetime.fromtimestamp(start)} to {datetime.fromtimestamp(end)}")
print(f"Duration: 7 days")
print()

# Tokens to test
tokens = ["IP", "KAITO", "APT", "TRUMP"]

# Load funding data
print("Loading funding data...")
print()

# Load combined files
extended_file = funding_data_path / "extended_historical_31d_cleaned.parquet"
lighter_file = funding_data_path / "lighter_historical_31d_cleaned.parquet"

extended_df = pd.read_parquet(extended_file)
lighter_df = pd.read_parquet(lighter_file)

print(f"Extended data: {len(extended_df)} rows")
print(f"Lighter data: {len(lighter_df)} rows")
print()

# Filter by time and tokens
extended_df = extended_df[
    (extended_df['timestamp'] >= start) &
    (extended_df['timestamp'] <= end) &
    (extended_df['base'].isin(tokens))
].copy()

lighter_df = lighter_df[
    (lighter_df['timestamp'] >= start) &
    (lighter_df['timestamp'] <= end) &
    (lighter_df['base'].isin(tokens))
].copy()

print(f"After filtering: Extended {len(extended_df)} rows, Lighter {len(lighter_df)} rows")
print()

all_data = []

for token in tokens:
    ext_token = extended_df[extended_df['base'] == token].copy()
    light_token = lighter_df[lighter_df['base'] == token].copy()

    print(f"{token:8} Extended: {len(ext_token):4} rows, Lighter: {len(light_token):4} rows")

    if ext_token.empty or light_token.empty:
        print(f"         ❌ Missing data!")
        continue

    # Merge on timestamp
    merged = pd.merge(
        ext_token[['timestamp', 'funding_rate']],
        light_token[['timestamp', 'funding_rate']],
        on='timestamp',
        suffixes=('_extended', '_lighter')
    )

    if merged.empty:
        print(f"         ❌ No overlapping timestamps!")
        continue

    # Calculate spread
    merged['spread'] = abs(merged['funding_rate_extended'] - merged['funding_rate_lighter'])
    merged['spread_pct'] = merged['spread'] * 100
    merged['token'] = token
    merged['datetime'] = pd.to_datetime(merged['timestamp'], unit='s')

    all_data.append(merged)

    print(f"         ✅ {len(merged)} matching timestamps")

print()

if not all_data:
    print("❌ No data loaded!")
    exit(1)

# Combine all
df = pd.concat(all_data, ignore_index=True)

print("="*80)
print("SPREAD ANALYSIS")
print("="*80)
print()

# Overall stats
print(f"Total data points: {len(df)}")
print(f"Date range: {df['datetime'].min()} to {df['datetime'].max()}")
print()

# Threshold levels
thresholds = [0.0005, 0.001, 0.0015, 0.002, 0.0025, 0.003]

print("OPPORTUNITIES BY THRESHOLD:")
print("="*80)
print()

for threshold in thresholds:
    threshold_pct = threshold * 100

    print(f"Threshold: {threshold:.4%}")
    print("-"*80)

    opportunities = df[df['spread'] >= threshold]

    if not opportunities.empty:
        by_token = opportunities.groupby('token').agg({
            'spread': ['count', 'mean', 'max'],
            'spread_pct': ['mean', 'max']
        }).round(6)

        by_token.columns = ['count', 'mean_spread', 'max_spread', 'mean_pct', 'max_pct']

        print(by_token.to_string())
        print()
        print(f"Total: {len(opportunities)} opportunities across {opportunities['token'].nunique()} tokens")
    else:
        print("No opportunities at this threshold")

    print()

# Show some example opportunities
print("="*80)
print("SAMPLE OPPORTUNITIES AT 0.30% THRESHOLD")
print("="*80)
print()

sample_opps = df[df['spread'] >= 0.003].nlargest(20, 'spread')

if not sample_opps.empty:
    print(sample_opps[[
        'datetime', 'token', 'spread_pct',
        'funding_rate_extended', 'funding_rate_lighter'
    ]].to_string(index=False))
    print()
else:
    print("No opportunities found at 0.30% threshold during this week!")
    print()
    print("Highest spreads detected:")
    top = df.nlargest(20, 'spread')
    print(top[[
        'datetime', 'token', 'spread_pct',
        'funding_rate_extended', 'funding_rate_lighter'
    ]].to_string(index=False))
    print()

# Check execution delay impact
print("="*80)
print("EXECUTION DELAY IMPACT (120 seconds)")
print("="*80)
print()

print("Simulating 120-second delay effect on opportunity detection...")
print()

# For each hour, check if opportunity exists at T-120s
df_sorted = df.sort_values(['token', 'timestamp'])

# Round to hourly intervals
df_sorted['hour'] = (df_sorted['timestamp'] // 3600) * 3600

delayed_opportunities = []

for token in tokens:
    token_data = df_sorted[df_sorted['token'] == token].copy()

    for hour in token_data['hour'].unique():
        # Decision time is 2 minutes before the hour
        decision_time = hour - 120

        # What data is available at decision time?
        available_data = token_data[token_data['timestamp'] <= decision_time]

        if available_data.empty:
            continue

        # Most recent data point
        latest = available_data.iloc[-1]

        # Check if this meets threshold
        if latest['spread'] >= 0.003:  # 0.30%
            delayed_opportunities.append({
                'hour': hour,
                'datetime': datetime.fromtimestamp(hour).isoformat(),
                'token': token,
                'spread': latest['spread'],
                'spread_pct': latest['spread_pct'],
                'data_age_seconds': decision_time - latest['timestamp']
            })

delayed_df = pd.DataFrame(delayed_opportunities)

if not delayed_df.empty:
    print(f"Opportunities detected with 120s delay: {len(delayed_df)}")
    print()

    by_token = delayed_df.groupby('token').agg({
        'spread': ['count', 'mean'],
        'data_age_seconds': 'mean'
    }).round(2)

    by_token.columns = ['count', 'mean_spread', 'avg_data_age_sec']
    print(by_token.to_string())
    print()
else:
    print("❌ NO opportunities detected with 120s execution delay!")
    print()
    print("This suggests the delay causes us to miss opportunities.")
    print()

print("="*80)
print("CONCLUSION")
print("="*80)
print()

# Compare: raw opportunities vs delayed opportunities
raw_opps_030 = len(df[df['spread'] >= 0.003])
delayed_opps_030 = len(delayed_df) if not delayed_df.empty else 0

print(f"Raw opportunities (0.30% threshold): {raw_opps_030}")
print(f"Opportunities with 120s delay: {delayed_opps_030}")
print(f"Capture rate: {delayed_opps_030 / raw_opps_030 * 100:.1f}%" if raw_opps_030 > 0 else "N/A")
print()

if delayed_opps_030 < raw_opps_030:
    print("⚠️ Execution delay is causing opportunity loss!")
    print()

print("Expected executors in backtest: {}".format(delayed_opps_030 * 2))
print("(Each opportunity creates 2 executors: LONG + SHORT)")
print()
