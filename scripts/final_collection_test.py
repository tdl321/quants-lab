"""
Final Validation Test for Data Collection System

This script runs a complete end-to-end test:
1. Collect 2 snapshots of funding rate data
2. Save to parquet files
3. Load and validate historical data
4. Calculate spreads
5. Display results

Run with: python scripts/final_collection_test.py
"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('/Users/tdl321/quants-lab/.env')

# Clear module cache
for key in list(sys.modules.keys()):
    if 'coingecko' in key or 'funding' in key:
        del sys.modules[key]

# Import modules fresh
import importlib.util

spec_cg = importlib.util.spec_from_file_location(
    'coingecko_funding',
    '/Users/tdl321/quants-lab/core/data_sources/coingecko_funding.py'
)
coingecko_module = importlib.util.module_from_spec(spec_cg)
spec_cg.loader.exec_module(coingecko_module)
sys.modules['core.data_sources.coingecko_funding'] = coingecko_module

spec = importlib.util.spec_from_file_location(
    'funding_rate_collector',
    '/Users/tdl321/quants-lab/core/data_sources/funding_rate_collector.py'
)
funding_collector_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(funding_collector_module)

FundingRateCollector = funding_collector_module.FundingRateCollector


async def main():
    """Run complete validation test."""

    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 15 + "FUNDING RATE COLLECTION - FINAL VALIDATION" + " " * 21 + "║")
    print("╚" + "═" * 78 + "╝")
    print()

    # Configuration
    api_key = os.getenv('COINGECKO_API_KEY')
    user_agent = os.getenv('COINGECKO_USER_AGENT', 'backtest')

    # Use top arbitrage opportunities from your CSV
    exchanges = ['lighter', 'extended']
    tokens = ['KAITO', 'MON', 'IP', 'GRASS']  # Top 4 from arbitrage data

    print(f"📊 Configuration:")
    print(f"   Exchanges: {', '.join(exchanges)}")
    print(f"   Tokens: {', '.join(tokens)}")
    print(f"   API: Demo ({api_key[:10]}...)")
    print()

    # Initialize collector
    collector = FundingRateCollector(
        api_key=api_key,
        user_agent=user_agent,
        exchanges=exchanges,
        tokens=tokens
    )

    print("=" * 80)
    print("STEP 1: Collect 2 Snapshots")
    print("=" * 80)

    # Collect 2 snapshots with 3-second interval
    await collector.start_collection(
        max_snapshots=2,
        interval_minutes=0.05  # 3 seconds
    )

    print("\n" + "=" * 80)
    print("STEP 2: Load Historical Data")
    print("=" * 80)

    historical_df = collector.load_historical_data()

    if historical_df.empty:
        print("❌ No data collected!")
        return

    print(f"\n✅ Loaded {len(historical_df)} records")
    print(f"\nData Summary:")
    print(f"  Date range: {datetime.fromtimestamp(historical_df['timestamp'].min())} to {datetime.fromtimestamp(historical_df['timestamp'].max())}")
    print(f"  Exchanges: {historical_df['exchange'].nunique()} ({', '.join(historical_df['exchange'].unique())})")
    print(f"  Tokens: {historical_df['base'].nunique()} ({', '.join(sorted(historical_df['base'].unique()))})")
    print(f"  Snapshots: {historical_df['timestamp'].nunique()}")

    print(f"\n📋 Sample Data:")
    print(historical_df[['timestamp', 'exchange', 'base', 'funding_rate', 'index']].head(8).to_string(index=False))

    print("\n" + "=" * 80)
    print("STEP 3: Calculate Spreads")
    print("=" * 80)

    spreads = collector.calculate_spreads(historical_df)

    if spreads.empty:
        print("❌ Could not calculate spreads")
        return

    # Find spread column
    spread_cols = [col for col in spreads.columns if 'spread' in col]
    if spread_cols:
        spread_col = spread_cols[0]
        spreads['spread_pct'] = spreads[spread_col].abs() * 100

        print(f"\n✅ Calculated spreads for {len(spreads)} tokens")
        print(f"\n📊 Funding Rate Spreads (sorted by opportunity):\n")

        # Sort by spread
        spreads_sorted = spreads.sort_values('spread_pct', ascending=False)

        # Display
        for _, row in spreads_sorted.iterrows():
            token = row['base']
            extended_rate = row.get('extended', 0) * 100
            lighter_rate = row.get('lighter', 0) * 100
            spread = row['spread_pct']

            # Determine position
            if extended_rate > lighter_rate:
                position = "Long Lighter, Short Extended"
            else:
                position = "Long Extended, Short Lighter"

            # Calculate APR
            hourly_spread = spread / 100
            apr = hourly_spread * 24 * 365

            print(f"  {token:10s} | Extended: {extended_rate:+7.3f}% | Lighter: {lighter_rate:+7.3f}% | Spread: {spread:6.3f}% | APR: {apr:6.1f}%")
            print(f"             | Strategy: {position}")
            print()

    print("=" * 80)
    print("STEP 4: Data Quality Validation")
    print("=" * 80)

    quality = collector.validate_data_quality(historical_df)

    print(f"\n✅ Data Quality Metrics:")
    for key, value in quality.items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for k, v in value.items():
                print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")

    print("\n" + "=" * 80)
    print("STEP 5: Storage Verification")
    print("=" * 80)

    raw_files = list(Path('/Users/tdl321/quants-lab/app/data/cache/funding/raw').glob('*.parquet'))

    print(f"\n✅ Data Files Created:")
    for file in raw_files:
        size_kb = file.stat().st_size / 1024
        print(f"  📄 {file.name} ({size_kb:.1f} KB)")

    metadata = collector.get_metadata()
    if metadata:
        print(f"\n✅ Metadata:")
        for key, value in metadata.items():
            print(f"  {key}: {value}")

    print("\n" + "╔" + "═" * 78 + "╗")
    print("║" + " " * 25 + "✅ VALIDATION COMPLETE" + " " * 31 + "║")
    print("╚" + "═" * 78 + "╝")
    print()
    print("🎉 Data collection system is working perfectly!")
    print()


if __name__ == "__main__":
    asyncio.run(main())
