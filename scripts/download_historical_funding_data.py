"""
Download Historical Funding Rate Data

Downloads 31 days of funding rate data from both Extended and Lighter DEXs
for all 10 target tokens. Saves to parquet files for backtesting.

Usage:
    python scripts/download_historical_funding_data.py

Output:
    - app/data/cache/funding/raw/extended_historical_31d.parquet
    - app/data/cache/funding/raw/lighter_historical_31d.parquet
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.data_sources.extended_funding import ExtendedFundingDataSource
from core.data_sources.lighter_funding import LighterFundingDataSource


# Configuration
TARGET_TOKENS = ['KAITO', 'IP', 'GRASS', 'ZEC', 'APT', 'SUI', 'TRUMP', 'LDO', 'OP', 'SEI']
DAYS = 31  # Match Lighter's available history
OUTPUT_DIR = project_root / 'app' / 'data' / 'cache' / 'funding' / 'raw'


async def download_extended_data():
    """Download 31 days of data from Extended."""
    print("=" * 80)
    print("DOWNLOADING FROM EXTENDED DEX")
    print("=" * 80)
    print()

    source = ExtendedFundingDataSource()
    await source.start()

    try:
        print(f"Tokens: {', '.join(TARGET_TOKENS)}")
        print(f"Period: {DAYS} days")
        print(f"Expected records: {len(TARGET_TOKENS)} tokens × {DAYS} days × 24 hours = {len(TARGET_TOKENS) * DAYS * 24}")
        print()

        df = await source.bulk_download_historical(
            tokens=TARGET_TOKENS,
            days=DAYS
        )

        if df.empty:
            print("❌ No data received from Extended")
            return None

        # Save to parquet
        output_file = OUTPUT_DIR / 'extended_historical_31d.parquet'
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(output_file, index=False)

        print()
        print(f"✅ Saved to: {output_file}")
        print(f"   Records: {len(df)}")
        print(f"   File size: {output_file.stat().st_size / 1024:.1f} KB")
        print(f"   Date range: {datetime.fromtimestamp(df['timestamp'].min())} to {datetime.fromtimestamp(df['timestamp'].max())}")
        print(f"   Exchanges: {df['exchange'].unique().tolist()}")
        print(f"   Tokens: {sorted(df['base'].unique().tolist())}")

        return df

    finally:
        await source.stop()


async def download_lighter_data():
    """Download 31 days of data from Lighter."""
    print()
    print("=" * 80)
    print("DOWNLOADING FROM LIGHTER DEX")
    print("=" * 80)
    print()

    source = LighterFundingDataSource()
    await source.start()

    try:
        print(f"Tokens: {', '.join(TARGET_TOKENS)}")
        print(f"Period: {DAYS} days")
        print(f"Expected records: {len(TARGET_TOKENS)} tokens × {DAYS} days × 24 hours = {len(TARGET_TOKENS) * DAYS * 24}")
        print()

        df = await source.bulk_download_historical(
            tokens=TARGET_TOKENS,
            days=DAYS
        )

        if df.empty:
            print("❌ No data received from Lighter")
            return None

        # Save to parquet
        output_file = OUTPUT_DIR / 'lighter_historical_31d.parquet'
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(output_file, index=False)

        print()
        print(f"✅ Saved to: {output_file}")
        print(f"   Records: {len(df)}")
        print(f"   File size: {output_file.stat().st_size / 1024:.1f} KB")
        print(f"   Date range: {datetime.fromtimestamp(df['timestamp'].min())} to {datetime.fromtimestamp(df['timestamp'].max())}")
        print(f"   Exchanges: {df['exchange'].unique().tolist()}")
        print(f"   Tokens: {sorted(df['base'].unique().tolist())}")

        return df

    finally:
        await source.stop()


async def verify_data_alignment(extended_df, lighter_df):
    """Verify both datasets are aligned and comparable."""
    print()
    print("=" * 80)
    print("DATA VERIFICATION")
    print("=" * 80)
    print()

    if extended_df is None or lighter_df is None:
        print("⚠️  One or both datasets are empty, cannot verify alignment")
        return

    # Check time ranges
    ext_start = datetime.fromtimestamp(extended_df['timestamp'].min())
    ext_end = datetime.fromtimestamp(extended_df['timestamp'].max())
    lit_start = datetime.fromtimestamp(lighter_df['timestamp'].min())
    lit_end = datetime.fromtimestamp(lighter_df['timestamp'].max())

    print(f"Extended date range: {ext_start} to {ext_end}")
    print(f"Lighter date range:  {lit_start} to {lit_end}")
    print()

    # Calculate overlap
    overlap_start = max(extended_df['timestamp'].min(), lighter_df['timestamp'].min())
    overlap_end = min(extended_df['timestamp'].max(), lighter_df['timestamp'].max())

    if overlap_start <= overlap_end:
        overlap_hours = (overlap_end - overlap_start) / 3600
        overlap_days = overlap_hours / 24
        print(f"✅ Overlapping period: {overlap_hours:.0f} hours ({overlap_days:.1f} days)")
        print(f"   Start: {datetime.fromtimestamp(overlap_start)}")
        print(f"   End: {datetime.fromtimestamp(overlap_end)}")
    else:
        print("❌ No overlapping time period!")
        return

    print()

    # Check token coverage
    ext_tokens = set(extended_df['base'].unique())
    lit_tokens = set(lighter_df['base'].unique())
    common_tokens = ext_tokens & lit_tokens
    missing_from_lighter = ext_tokens - lit_tokens
    missing_from_extended = lit_tokens - ext_tokens

    print(f"Token coverage:")
    print(f"   Extended: {len(ext_tokens)} tokens - {sorted(ext_tokens)}")
    print(f"   Lighter: {len(lit_tokens)} tokens - {sorted(lit_tokens)}")
    print(f"   Common: {len(common_tokens)} tokens - {sorted(common_tokens)}")

    if missing_from_lighter:
        print(f"   ⚠️  Missing from Lighter: {sorted(missing_from_lighter)}")
    if missing_from_extended:
        print(f"   ⚠️  Missing from Extended: {sorted(missing_from_extended)}")

    print()

    # Check for sample spreads in overlap period
    if common_tokens:
        print("Sample arbitrage opportunities (in overlapping period):")
        print()

        # Get overlap data
        ext_overlap = extended_df[
            (extended_df['timestamp'] >= overlap_start) &
            (extended_df['timestamp'] <= overlap_end)
        ]
        lit_overlap = lighter_df[
            (lighter_df['timestamp'] >= overlap_start) &
            (lighter_df['timestamp'] <= overlap_end)
        ]

        # Check one timestamp for each token
        sample_timestamp = overlap_start

        for token in sorted(list(common_tokens))[:5]:  # Show first 5
            ext_rate = ext_overlap[
                (ext_overlap['timestamp'] == sample_timestamp) &
                (ext_overlap['base'] == token)
            ]['funding_rate'].values

            lit_rate = lit_overlap[
                (lit_overlap['timestamp'] == sample_timestamp) &
                (lit_overlap['base'] == token)
            ]['funding_rate'].values

            if len(ext_rate) > 0 and len(lit_rate) > 0:
                spread = abs(ext_rate[0] - lit_rate[0])
                apr = spread * 24 * 365 * 100

                print(f"  {token:8s}: Extended={ext_rate[0]:+.6f}, Lighter={lit_rate[0]:+.6f}, "
                      f"Spread={spread:.6f} ({apr:.1f}% APR)")

    print()
    print("=" * 80)
    print("✅ DATA DOWNLOAD COMPLETE")
    print("=" * 80)
    print()
    print(f"Total records: {len(extended_df) + len(lighter_df)}")
    print(f"Storage location: {OUTPUT_DIR}")
    print()
    print("You can now use FundingRateBacktestDataProvider to load this data:")
    print(">>> provider = FundingRateBacktestDataProvider()")
    print(">>> provider.load_data()")


async def main():
    """Main execution."""
    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 15 + "HISTORICAL FUNDING RATE DATA DOWNLOAD" + " " * 25 + "║")
    print("╚" + "═" * 78 + "╝")
    print()

    try:
        # Download from Extended
        extended_df = await download_extended_data()

        # Download from Lighter
        lighter_df = await download_lighter_data()

        # Verify alignment
        await verify_data_alignment(extended_df, lighter_df)

        return True

    except Exception as e:
        print()
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
