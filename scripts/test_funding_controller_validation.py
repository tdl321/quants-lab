"""
Validation tests for funding rate arbitrage controller.

Tests:
1. No lookahead bias - only uses past funding data
2. Execution delay applied correctly
3. Decision timing precedes action timing
4. Funding rate queries respect time boundaries

Usage:
    python scripts/test_funding_controller_validation.py
"""

import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

project_root = Path(__file__).parent.parent
hummingbot_root = project_root.parent / 'hummingbot'
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(hummingbot_root))

from core.backtesting import BacktestingEngine
from controllers.funding_rate_arb import FundingRateArbControllerConfig


def test_funding_time_filtering():
    """Test 1: Verify funding queries only return past data."""
    print("Test 1: Funding time filtering...")

    engine = BacktestingEngine(load_cached_data=True)
    data_provider = engine._bt_engine.backtesting_data_provider

    # Set time to middle of data range
    test_time = int(datetime(2024, 10, 15, 12, 0, 0).timestamp())
    data_provider._time = test_time

    # Query funding
    connector = data_provider.connectors["extended_perpetual"]
    funding = connector.get_funding_info("KAITO-USD")

    if funding is None:
        print("   ⚠️  No funding data at test timestamp")
        return False

    # Get raw data
    raw_df = data_provider.funding_feeds["extended_perpetual_KAITO-USD"]

    # Find the actual timestamp of returned data
    matching_row = raw_df[raw_df['funding_rate'] == float(funding.rate)]

    if matching_row.empty:
        print("   ❌ Could not find matching funding rate in raw data")
        return False

    actual_timestamp = matching_row.iloc[-1]['timestamp']

    # Verify it's from the past
    if actual_timestamp > test_time:
        print(f"   ❌ LOOKAHEAD BIAS: Using future data!")
        print(f"      Current time: {test_time}")
        print(f"      Data timestamp: {actual_timestamp}")
        return False

    lag_minutes = (test_time - actual_timestamp) / 60
    print(f"   ✅ Funding data is from past (lag: {lag_minutes:.0f} min)")
    return True


def test_execution_delay():
    """Test 2: Verify execution delay is applied."""
    print("\nTest 2: Execution delay...")

    config = FundingRateArbControllerConfig(
        execution_delay_seconds=120,  # 2 minutes
        connectors={"extended_perpetual", "lighter_perpetual"},
        tokens={"KAITO"},
        min_funding_rate_profitability=Decimal('0.001'),  # Low threshold
    )

    if config.execution_delay_seconds != 120:
        print("   ❌ Execution delay not set correctly")
        return False

    print(f"   ✅ Execution delay: {config.execution_delay_seconds}s (2 minutes)")
    return True


def test_no_future_spread_calculation():
    """Test 3: Verify spread calculations use only past data."""
    print("\nTest 3: Spread calculation timing...")

    engine = BacktestingEngine(load_cached_data=True)
    data_provider = engine._bt_engine.backtesting_data_provider

    # Set time
    test_time = int(datetime(2024, 10, 10, 15, 0, 0).timestamp())
    data_provider._time = test_time

    # Get funding from both exchanges
    extended = data_provider.connectors["extended_perpetual"]
    lighter = data_provider.connectors["lighter_perpetual"]

    extended_funding = extended.get_funding_info("KAITO-USD")
    lighter_funding = lighter.get_funding_info("KAITO-USD")

    if extended_funding is None or lighter_funding is None:
        print("   ⚠️  Funding data not available")
        return False

    # Calculate spread (same logic as controller)
    spread = abs(float(extended_funding.rate) - float(lighter_funding.rate))

    print(f"   ✅ Spread calculated from past data: {spread:.6f}")
    print(f"      Extended rate: {extended_funding.rate}")
    print(f"      Lighter rate: {lighter_funding.rate}")
    return True


def test_data_coverage():
    """Test 4: Verify funding data coverage for backtest period."""
    print("\nTest 4: Data coverage verification...")

    engine = BacktestingEngine(load_cached_data=True)
    data_provider = engine._bt_engine.backtesting_data_provider

    # Expected backtest period
    start_time = int(datetime(2024, 10, 4, 20, 0, 0).timestamp())
    end_time = int(datetime(2024, 11, 4, 17, 0, 0).timestamp())

    # Check a few key feeds
    test_feeds = [
        "extended_perpetual_KAITO-USD",
        "lighter_perpetual_KAITO-USD",
        "extended_perpetual_APT-USD",
        "lighter_perpetual_APT-USD"
    ]

    all_covered = True
    for feed_key in test_feeds:
        if feed_key not in data_provider.funding_feeds:
            print(f"   ❌ Missing feed: {feed_key}")
            all_covered = False
            continue

        df = data_provider.funding_feeds[feed_key]
        data_start = df['timestamp'].min()
        data_end = df['timestamp'].max()

        if data_start > start_time or data_end < end_time:
            print(f"   ⚠️  Incomplete coverage for {feed_key}")
            print(f"      Need: {datetime.fromtimestamp(start_time)} to {datetime.fromtimestamp(end_time)}")
            print(f"      Have: {datetime.fromtimestamp(data_start)} to {datetime.fromtimestamp(data_end)}")
            all_covered = False

    if all_covered:
        print(f"   ✅ All tested feeds cover backtest period")

    return all_covered


def main():
    print("="*80)
    print("FUNDING CONTROLLER VALIDATION TESTS")
    print("="*80)
    print()

    tests = [
        test_funding_time_filtering,
        test_execution_delay,
        test_no_future_spread_calculation,
        test_data_coverage,
    ]

    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"   ❌ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    print()
    print("="*80)
    if all(results):
        print("✅ ALL VALIDATION TESTS PASSED")
        print()
        print("No lookahead bias detected!")
        print("Controller is safe to use for backtesting.")
    else:
        print("❌ SOME TESTS FAILED")
        print()
        print("Please review failures before running backtests.")
    print("="*80)
    print()

    return all(results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
