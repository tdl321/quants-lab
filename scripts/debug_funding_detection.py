"""
Debug: Why isn't the controller detecting funding opportunities?

Tests if funding data is actually accessible to the controller.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add paths
project_root = Path(__file__).parent.parent
hummingbot_root = project_root.parent / 'hummingbot'

for path in [str(project_root), str(hummingbot_root)]:
    while path in sys.path:
        sys.path.remove(path)

sys.path.insert(0, str(project_root))
sys.path.insert(1, str(hummingbot_root))

from controllers.funding_rate_arb import FundingRateArbControllerConfig
from core.backtesting.multi_connector_engine import MultiConnectorBacktestingEngine
from core.backtesting import BacktestingEngine


async def main():
    print()
    print("="*80)
    print("DEBUG: FUNDING DATA DETECTION")
    print("="*80)
    print()

    # Initialize engine
    print("Initializing engine with funding data...")
    custom_engine = MultiConnectorBacktestingEngine()
    backtesting = BacktestingEngine(
        load_cached_data=True,
        custom_backtester=custom_engine
    )
    print()

    # Check what funding data was loaded
    data_provider = backtesting._bt_engine.backtesting_data_provider

    print("FUNDING FEEDS LOADED:")
    print("="*80)
    if hasattr(data_provider, 'funding_feeds'):
        print(f"Total feeds: {len(data_provider.funding_feeds)}")
        print()
        for feed_key in sorted(data_provider.funding_feeds.keys()):
            df = data_provider.funding_feeds[feed_key]
            print(f"{feed_key:40} {len(df):5} records")
    else:
        print("❌ NO funding_feeds attribute!")
    print()

    # Test get_funding_info directly
    print("TESTING get_funding_info():")
    print("="*80)

    # Set a timestamp where we know IP has an opportunity
    # 2025-10-10 19:00:00 - IP has 1.9187% spread
    test_time = int(datetime(2025, 10, 10, 19, 0, 0).timestamp())
    data_provider._time = test_time

    print(f"Test timestamp: {datetime.fromtimestamp(test_time)}")
    print()

    for connector in ['extended_perpetual', 'lighter_perpetual']:
        for token in ['IP', 'KAITO', 'ZEC']:
            trading_pair = f"{token}-USD"

            funding_info = data_provider.get_funding_info(connector, trading_pair)

            if funding_info:
                print(f"{connector:25} {trading_pair:12} rate={funding_info.rate:.6f}")
            else:
                print(f"{connector:25} {trading_pair:12} ❌ None")

    print()

    # Calculate spreads
    print("CALCULATED SPREADS:")
    print("="*80)
    for token in ['IP', 'KAITO', 'ZEC']:
        trading_pair = f"{token}-USD"

        ext_info = data_provider.get_funding_info('extended_perpetual', trading_pair)
        light_info = data_provider.get_funding_info('lighter_perpetual', trading_pair)

        if ext_info and light_info:
            spread = abs(float(ext_info.rate) - float(light_info.rate))
            qualifies = spread >= 0.003
            status = "✅ QUALIFIES" if qualifies else "❌ Too small"
            print(f"{token:8} spread={spread:.6f} ({spread*100:.4f}%) {status}")
        else:
            print(f"{token:8} ❌ Missing funding data")

    print()

    # Now run actual backtest on just this one hour
    print("="*80)
    print("RUNNING BACKTEST ON SINGLE HOUR")
    print("="*80)
    print()

    config = FundingRateArbControllerConfig(
        controller_name="funding_rate_arb",
        connector_name="extended_perpetual",
        trading_pair="IP-USD",

        connectors={"extended_perpetual", "lighter_perpetual"},
        tokens={"IP", "KAITO"},

        leverage=5,
        min_funding_rate_profitability=Decimal('0.003'),
        position_size_quote=Decimal('500'),

        absolute_min_spread_exit=Decimal('0.0003'),
        compression_exit_threshold=Decimal('0.4'),
        max_position_duration_hours=24,
        max_loss_per_position_pct=Decimal('0.03'),

        execution_delay_seconds=120,
    )

    # Just one hour around the known opportunity
    start = int(datetime(2025, 10, 10, 19, 0, 0).timestamp())
    end = int(datetime(2025, 10, 10, 20, 0, 0).timestamp())

    print(f"Period: {datetime.fromtimestamp(start)} to {datetime.fromtimestamp(end)}")
    print(f"Tokens: IP (1.9187% spread), KAITO")
    print()

    result = await backtesting.run_backtesting(
        config,
        start,
        end,
        backtesting_resolution="1h",
        trade_cost=0.0
    )

    results_dict = result.results
    num_executors = results_dict['total_executors']

    print()
    print("RESULT:")
    print("="*80)
    print(f"Executors created: {num_executors}")
    print(f"Expected: 2 (1 IP opportunity × 2 executors)")
    print()

    if num_executors == 0:
        print("❌ PROBLEM: No executors created despite 1.9187% spread!")
        print()
        print("This confirms the controller is NOT detecting opportunities")
        print("even when funding data exists and shows qualifying spreads.")
    else:
        print(f"✅ SUCCESS: Created {num_executors} executors")
        executors_df = result.executors_df
        if not executors_df.empty:
            executors_df['token'] = executors_df['config'].apply(
                lambda x: x.get('trading_pair', '').split('-')[0]
            )
            print(f"Tokens: {executors_df['token'].unique()}")


if __name__ == "__main__":
    asyncio.run(main())
