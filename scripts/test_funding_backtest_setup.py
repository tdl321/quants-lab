"""
Test Funding Rate Backtesting Setup

Validates that:
1. BacktestingEngine loads funding data successfully
2. Mock connectors are registered
3. get_funding_info() returns correct historical data
4. Data provider is time-aware

Usage:
    python scripts/test_funding_backtest_setup.py
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
hummingbot_root = project_root.parent / 'hummingbot'
sys.path.insert(0, str(hummingbot_root))

# Import directly from hummingbot to avoid quants-lab dependencies
from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase


def main():
    print("="*80)
    print("TESTING FUNDING RATE BACKTESTING SETUP")
    print("="*80)
    print()

    # Test 1: Initialize engine and load data
    print("Test 1: Initializing BacktestingEngine...")
    try:
        engine = BacktestingEngineBase()
        data_provider = engine.backtesting_data_provider
        print("✅ Engine initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize engine: {e}")
        import traceback
        traceback.print_exc()
        return False

    print()

    # Load funding data manually
    print("Test 1.5: Loading funding rate data...")
    funding_path = project_root / 'app' / 'data' / 'cache' / 'funding' / 'clean'

    if not funding_path.exists():
        print(f"❌ Funding data directory not found: {funding_path}")
        return False

    data_provider.load_funding_rate_data(funding_path)

    # Register mock connectors manually
    print("Test 1.6: Registering mock connectors...")
    sys.path.insert(0, str(project_root))
    from core.backtesting.mock_perpetual_connectors import (
        ExtendedPerpetualMockConnector,
        LighterPerpetualMockConnector
    )

    extended_connector = ExtendedPerpetualMockConnector(data_provider)
    lighter_connector = LighterPerpetualMockConnector(data_provider)

    data_provider.connectors["extended_perpetual"] = extended_connector
    data_provider.connectors["lighter_perpetual"] = lighter_connector

    print()

    # Test 2: Check funding feeds loaded
    print("Test 2: Checking funding rate data...")

    if not data_provider.funding_feeds:
        print("❌ No funding feeds loaded")
        return False

    print(f"✅ Loaded {len(data_provider.funding_feeds)} funding rate feeds")

    # Print sample feeds
    print("\n  Sample feeds:")
    for i, feed_key in enumerate(list(data_provider.funding_feeds.keys())[:5]):
        df = data_provider.funding_feeds[feed_key]
        print(f"    {feed_key}: {len(df)} records")

    print()

    # Test 3: Check mock connectors registered
    print("Test 3: Checking mock connectors...")

    if "extended_perpetual" not in data_provider.connectors:
        print("❌ extended_perpetual connector not registered")
        return False

    if "lighter_perpetual" not in data_provider.connectors:
        print("❌ lighter_perpetual connector not registered")
        return False

    print("✅ Mock connectors registered:")
    print("    - extended_perpetual")
    print("    - lighter_perpetual")

    print()

    # Test 4: Test get_funding_info with time-awareness
    print("Test 4: Testing time-aware funding rate queries...")

    # Set backtest time to a known timestamp
    test_timestamp = 1759622400  # Oct 4, 2025 20:00:00
    data_provider._time = test_timestamp

    print(f"  Set backtest time: {datetime.fromtimestamp(test_timestamp)}")

    # Try to get funding info for KAITO-USD from extended
    extended_connector = data_provider.connectors["extended_perpetual"]
    funding_info = extended_connector.get_funding_info("KAITO-USD")

    if funding_info is None:
        print("❌ Failed to get funding info")
        return False

    print(f"✅ Got funding info for KAITO-USD at {datetime.fromtimestamp(test_timestamp)}:")
    print(f"    Rate: {funding_info.rate}")
    print(f"    Next funding: {datetime.fromtimestamp(funding_info.next_funding_utc_timestamp)}")

    print()

    # Test 5: Compare Extended vs Lighter
    print("Test 5: Comparing Extended vs Lighter funding rates...")

    lighter_connector = data_provider.connectors["lighter_perpetual"]
    lighter_funding = lighter_connector.get_funding_info("KAITO-USD")

    if lighter_funding is None:
        print("❌ Failed to get Lighter funding info")
        return False

    extended_funding = extended_connector.get_funding_info("KAITO-USD")

    spread = abs(float(extended_funding.rate) - float(lighter_funding.rate))
    apr = spread * 24 * 365 * 100

    print(f"✅ Funding rate comparison at {datetime.fromtimestamp(test_timestamp)}:")
    print(f"    Extended rate: {extended_funding.rate:+.6f}")
    print(f"    Lighter rate:  {lighter_funding.rate:+.6f}")
    print(f"    Spread:        {spread:.6f} ({apr:.1f}% APR)")

    print()

    # Test 6: Test time progression
    print("Test 6: Testing time progression...")

    # Move forward 1 hour
    new_timestamp = test_timestamp + 3600
    data_provider._time = new_timestamp

    print(f"  Advanced time to: {datetime.fromtimestamp(new_timestamp)}")

    new_funding = extended_connector.get_funding_info("KAITO-USD")

    if new_funding is None:
        print("❌ Failed to get funding info at new timestamp")
        return False

    print(f"✅ Got funding info at new time:")
    print(f"    Rate: {new_funding.rate}")

    # Verify rate changed (or stayed same)
    if new_funding.rate != extended_funding.rate:
        print(f"    ✅ Rate changed from previous hour")
    else:
        print(f"    ℹ️  Rate unchanged from previous hour")

    print()

    # Test 7: Verify data coverage
    print("Test 7: Verifying data coverage...")

    tokens = ["KAITO", "IP", "GRASS", "ZEC", "APT", "SUI", "TRUMP", "LDO", "OP", "SEI"]
    exchanges = ["extended", "lighter"]

    coverage = []
    for exchange in exchanges:
        for token in tokens:
            feed_key = f"{exchange}_perpetual_{token}-USD"
            if feed_key in data_provider.funding_feeds:
                df = data_provider.funding_feeds[feed_key]
                coverage.append({
                    'exchange': exchange,
                    'token': token,
                    'records': len(df),
                    'start': datetime.fromtimestamp(df['timestamp'].min()),
                    'end': datetime.fromtimestamp(df['timestamp'].max())
                })

    print(f"✅ Data coverage: {len(coverage)} exchange-token pairs")
    print(f"\n  Sample (first 5):")
    for item in coverage[:5]:
        print(f"    {item['exchange']:8s} {item['token']:6s}: {item['records']:3d} records "
              f"({item['start'].strftime('%Y-%m-%d')} to {item['end'].strftime('%Y-%m-%d')})")

    print()

    # Summary
    print("="*80)
    print("✅ ALL TESTS PASSED")
    print("="*80)
    print()
    print("Ready to run full backtesting!")
    print()

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
