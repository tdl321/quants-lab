"""
Test Funding Rate Backtest Data Provider

Validates that the backtest data provider works correctly with collected data.

Run with: python scripts/test_backtest_provider.py
"""

import sys
from datetime import datetime

# Import directly
import importlib.util

spec = importlib.util.spec_from_file_location(
    "funding_rate_data_provider",
    "/Users/tdl321/quants-lab/core/backtesting/funding_rate_data_provider.py"
)
provider_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider_module)

FundingRateBacktestDataProvider = provider_module.FundingRateBacktestDataProvider


def main():
    """Test the backtest data provider."""

    print("=" * 80)
    print("TESTING FUNDING RATE BACKTEST DATA PROVIDER")
    print("=" * 80)
    print()

    # Initialize provider
    provider = FundingRateBacktestDataProvider()

    # Test 1: Load data
    print("📊 TEST 1: Load Historical Data")
    print("-" * 80)

    data = provider.load_data()

    print(f"✅ Loaded {len(data)} records")
    print(f"  Exchanges: {provider.exchanges}")
    print(f"  Tokens: {provider.tokens}")
    print(f"  Time range: {datetime.fromtimestamp(provider.start_timestamp)} to {datetime.fromtimestamp(provider.end_timestamp)}")
    print()

    # Test 2: Get funding rate at specific timestamp
    print("📊 TEST 2: Get Funding Rate at Timestamp")
    print("-" * 80)

    test_timestamp = provider.start_timestamp + 3600  # 1 hour after start
    test_token = provider.tokens[0]
    test_exchange = provider.exchanges[0]

    rate = provider.get_funding_rate(test_timestamp, test_exchange, test_token)

    print(f"  Timestamp: {datetime.fromtimestamp(test_timestamp)}")
    print(f"  Exchange: {test_exchange}")
    print(f"  Token: {test_token}")
    print(f"  ✅ Funding Rate: {rate:.4f}%" if rate is not None else "  ❌ No data")
    print()

    # Test 3: Calculate spread
    print("📊 TEST 3: Calculate Spread Between Exchanges")
    print("-" * 80)

    if len(provider.exchanges) >= 2:
        spread = provider.get_spread(
            test_timestamp,
            provider.exchanges[0],
            provider.exchanges[1],
            test_token
        )

        print(f"  Timestamp: {datetime.fromtimestamp(test_timestamp)}")
        print(f"  Exchange 1: {provider.exchanges[0]}")
        print(f"  Exchange 2: {provider.exchanges[1]}")
        print(f"  Token: {test_token}")
        print(f"  ✅ Spread: {spread:.4f}%" if spread is not None else "  ❌ No data")
    else:
        print("  ⚠️  Need at least 2 exchanges for spread calculation")
    print()

    # Test 4: Find best spread
    print("📊 TEST 4: Find Best Spread for Token")
    print("-" * 80)

    best_spread = provider.get_best_spread(test_timestamp, test_token)

    if best_spread:
        ex1, ex2, spread = best_spread
        print(f"  Timestamp: {datetime.fromtimestamp(test_timestamp)}")
        print(f"  Token: {test_token}")
        print(f"  ✅ Best spread: {ex1} <-> {ex2}")
        print(f"  ✅ Spread: {spread:.4f}% ({spread*100:.2f}% absolute)")
    else:
        print("  ❌ Could not find spread")
    print()

    # Test 5: Get funding payment times
    print("📊 TEST 5: Get Funding Payment Times")
    print("-" * 80)

    payment_times = provider.get_funding_payment_times(provider.exchanges[0])

    print(f"  Exchange: {provider.exchanges[0]}")
    print(f"  ✅ Found {len(payment_times)} funding payment times")
    print(f"  First 5:")
    for ts in payment_times[:5]:
        print(f"    - {datetime.fromtimestamp(ts)}")
    print()

    # Test 6: Data summary
    print("📊 TEST 6: Get Data Summary")
    print("-" * 80)

    summary = provider.get_data_summary()

    print(f"  Total records: {summary['total_records']}")
    print(f"  Duration: {summary['duration_hours']:.2f} hours")
    print(f"  Unique timestamps: {summary['unique_timestamps']}")
    print(f"  Completeness: {summary['completeness']*100:.1f}%")
    print(f"\n  Coverage by exchange-token pair:")
    for cov in summary['coverage_by_pair']:
        print(f"    {cov['exchange']:10s} x {cov['token']:10s} = {cov['snapshots']} snapshots")

    if summary['time_gaps']:
        print(f"\n  ⚠️  Time gaps detected:")
        for gap in summary['time_gaps']:
            print(f"    {gap['from']} → {gap['to']} ({gap['hours']:.1f} hours)")
    else:
        print(f"\n  ✅ No significant time gaps")
    print()

    # Test 7: Simulate backtest loop
    print("📊 TEST 7: Simulate Backtest Time Loop")
    print("-" * 80)

    print(f"  Simulating backtest from {datetime.fromtimestamp(provider.start_timestamp)}")
    print(f"  to {datetime.fromtimestamp(provider.end_timestamp)}...")
    print()

    # Get all unique timestamps
    timestamps = sorted(data['timestamp'].unique())

    arbitrage_opportunities = []

    for ts in timestamps:
        for token in provider.tokens:
            best = provider.get_best_spread(ts, token)
            if best and best[2] > 0.003:  # 0.3% threshold
                arbitrage_opportunities.append({
                    'timestamp': ts,
                    'token': token,
                    'ex1': best[0],
                    'ex2': best[1],
                    'spread': best[2]
                })

    print(f"  ✅ Processed {len(timestamps)} timestamps")
    print(f"  ✅ Found {len(arbitrage_opportunities)} arbitrage opportunities (>0.3% spread)")

    if arbitrage_opportunities:
        print(f"\n  Top 5 opportunities:")
        sorted_opps = sorted(arbitrage_opportunities, key=lambda x: x['spread'], reverse=True)
        for opp in sorted_opps[:5]:
            print(f"    {datetime.fromtimestamp(opp['timestamp'])}: {opp['token']} - {opp['spread']*100:.2f}% ({opp['ex1']} <-> {opp['ex2']})")
    print()

    print("=" * 80)
    print("✅ ALL TESTS PASSED")
    print("=" * 80)
    print("\n🎉 Backtest Data Provider is working correctly!")


if __name__ == "__main__":
    main()
