"""
Test Extended API Connectivity

This script tests the Extended data source to verify:
1. API connectivity
2. Market listing endpoint
3. Historical funding rate endpoint
4. Data format and schema

Run with: python scripts/test_extended_api.py
"""

import asyncio
import sys
import importlib.util
from pathlib import Path
from datetime import datetime, timedelta

# Load modules directly to avoid __init__.py issues
base_spec = importlib.util.spec_from_file_location(
    'base_funding_source',
    '/Users/tdl321/quants-lab/core/data_sources/base_funding_source.py'
)
base_module = importlib.util.module_from_spec(base_spec)
sys.modules['base_funding_source'] = base_module
sys.modules['core.data_sources.base_funding_source'] = base_module
base_spec.loader.exec_module(base_module)

extended_spec = importlib.util.spec_from_file_location(
    'extended_funding',
    '/Users/tdl321/quants-lab/core/data_sources/extended_funding.py'
)
extended_module = importlib.util.module_from_spec(extended_spec)
extended_spec.loader.exec_module(extended_module)

ExtendedFundingDataSource = extended_module.ExtendedFundingDataSource


async def test_markets_endpoint():
    """Test fetching available markets."""
    print("=" * 80)
    print("TEST 1: Fetch Available Markets")
    print("=" * 80)

    source = ExtendedFundingDataSource()

    try:
        await source.start()
        print(f"✅ Session started")
        print(f"✅ Markets fetched: {len(source.MARKET_MAPPINGS)}")

        # Show some markets
        if source.MARKET_MAPPINGS:
            print(f"\n📊 Sample Markets:")
            for i, (token, market_id) in enumerate(list(source.MARKET_MAPPINGS.items())[:10]):
                print(f"  {token:10s} -> {market_id}")

            # Check for our target tokens
            target_tokens = ['KAITO', 'MON', 'IP', 'GRASS', 'ZEC', 'APT', 'SUI', 'TRUMP', 'LDO', 'OP', 'SEI']
            found = [token for token in target_tokens if token in source.MARKET_MAPPINGS]

            print(f"\n🎯 Target Tokens Found: {len(found)}/{len(target_tokens)}")
            for token in found:
                print(f"  ✅ {token} -> {source.MARKET_MAPPINGS[token]}")

            missing = [token for token in target_tokens if token not in source.MARKET_MAPPINGS]
            if missing:
                print(f"\n⚠️  Missing Tokens: {', '.join(missing)}")

        return True

    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await source.stop()


async def test_historical_endpoint():
    """Test fetching historical funding rate data."""
    print("\n" + "=" * 80)
    print("TEST 2: Fetch Historical Funding Rates")
    print("=" * 80)

    source = ExtendedFundingDataSource()

    try:
        await source.start()

        # Test with KAITO (known to exist on Extended)
        test_market = "KAITO-USD"
        end_time = int(datetime.now().timestamp())
        start_time = end_time - (7 * 24 * 3600)  # 7 days

        print(f"\n📊 Fetching: {test_market}")
        print(f"   Time range: {datetime.fromtimestamp(start_time)} to {datetime.fromtimestamp(end_time)}")

        df = await source.get_historical_funding_rates(
            market=test_market,
            start_time=start_time,
            end_time=end_time,
            limit=1000
        )

        if df.empty:
            print(f"❌ No data returned for {test_market}")
            return False

        print(f"\n✅ Success! Downloaded {len(df)} records")
        print(f"\n📋 Data Schema:")
        print(f"   Columns: {list(df.columns)}")
        print(f"   Dtypes:\n{df.dtypes}")

        print(f"\n📊 Data Summary:")
        print(f"   Date range: {datetime.fromtimestamp(df['timestamp'].min())} to {datetime.fromtimestamp(df['timestamp'].max())}")
        print(f"   Exchange: {df['exchange'].unique()}")
        print(f"   Base: {df['base'].unique()}")
        print(f"   Target: {df['target'].unique()}")
        print(f"   Funding rate range: {df['funding_rate'].min():.6f} to {df['funding_rate'].max():.6f}")

        print(f"\n📋 Sample Records:")
        print(df.head().to_string(index=False))

        return True

    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await source.stop()


async def test_bulk_download():
    """Test bulk download for multiple tokens."""
    print("\n" + "=" * 80)
    print("TEST 3: Bulk Download (3 tokens, 7 days)")
    print("=" * 80)

    source = ExtendedFundingDataSource()

    try:
        await source.start()

        # Test with subset of tokens
        test_tokens = ['KAITO', 'IP', 'GRASS']

        print(f"\n📊 Downloading {len(test_tokens)} tokens: {', '.join(test_tokens)}")
        print(f"   Time range: Last 7 days")

        df = await source.bulk_download_historical(
            tokens=test_tokens,
            days=7
        )

        if df.empty:
            print(f"❌ No data returned")
            return False

        print(f"\n✅ Success! Downloaded {len(df)} total records")

        print(f"\n📊 Data Summary:")
        print(f"   Date range: {datetime.fromtimestamp(df['timestamp'].min())} to {datetime.fromtimestamp(df['timestamp'].max())}")
        print(f"   Tokens: {df['base'].nunique()} ({', '.join(sorted(df['base'].unique()))})")
        print(f"   Records per token:")
        for token in sorted(df['base'].unique()):
            count = len(df[df['base'] == token])
            date_range = df[df['base'] == token]['timestamp']
            print(f"     {token:10s}: {count:4d} records ({datetime.fromtimestamp(date_range.min())} to {datetime.fromtimestamp(date_range.max())})")

        print(f"\n📋 Sample Records from Each Token:")
        for token in sorted(df['base'].unique()):
            token_df = df[df['base'] == token].head(2)
            print(f"\n  {token}:")
            print(f"    {token_df[['timestamp', 'funding_rate', 'index']].to_string(index=False)}")

        return True

    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await source.stop()


async def main():
    """Run all tests."""
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "EXTENDED API CONNECTIVITY TEST" + " " * 28 + "║")
    print("╚" + "═" * 78 + "╝")
    print()

    results = {}

    # Test 1: Markets endpoint
    results['markets'] = await test_markets_endpoint()

    # Test 2: Historical endpoint (single token)
    results['historical'] = await test_historical_endpoint()

    # Test 3: Bulk download (multiple tokens)
    results['bulk'] = await test_bulk_download()

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test_name:15s}: {status}")

    all_passed = all(results.values())
    print()
    if all_passed:
        print("🎉 All tests passed! Extended API is ready for use.")
    else:
        print("⚠️  Some tests failed. Review errors above.")

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
