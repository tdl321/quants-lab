"""
Test Strategy WITHOUT ZEC

This diagnostic test removes ZEC to verify that other tokens (IP, KAITO, etc.)
do have tradeable spreads and would execute if not blocked by ZEC.

Usage:
    python scripts/test_without_zec.py
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
    print("DIAGNOSTIC TEST: STRATEGY WITHOUT ZEC")
    print("="*80)
    print()
    print("Hypothesis: ZEC blocks other tokens due to one-position-per-token limit")
    print("Test: Remove ZEC and see if IP, KAITO, APT, TRUMP trade")
    print()

    # Initialize engine
    print("Initializing engine...")
    custom_engine = MultiConnectorBacktestingEngine()
    backtesting = BacktestingEngine(
        load_cached_data=True,
        custom_backtester=custom_engine
    )
    print("✅ Engine initialized\n")

    # Configure WITHOUT ZEC
    print("Configuring strategy WITHOUT ZEC...")
    config = FundingRateArbControllerConfig(
        controller_name="funding_rate_arb",
        connector_name="extended_perpetual",
        trading_pair="KAITO-USD",

        connectors={"extended_perpetual", "lighter_perpetual"},
        # EXCLUDE ZEC - only use other 9 tokens
        tokens={"KAITO", "IP", "GRASS", "APT", "SUI", "TRUMP", "LDO", "OP", "SEI"},

        leverage=5,
        min_funding_rate_profitability=Decimal('0.0005'),  # 0.05% - very low threshold
        position_size_quote=Decimal('500'),

        absolute_min_spread_exit=Decimal('0.0003'),
        compression_exit_threshold=Decimal('0.4'),
        max_position_duration_hours=24,
        max_loss_per_position_pct=Decimal('0.03'),

        execution_delay_seconds=120,
    )

    print("✅ Configuration:")
    print(f"   Tokens: {', '.join(sorted(config.tokens))}")
    print(f"   Min spread: {config.min_funding_rate_profitability:.4%}")
    print(f"   ZEC EXCLUDED: Should see IP, KAITO, APT, TRUMP if they have spreads")
    print()

    # Backtest period
    start = int(datetime(2025, 10, 4, 20, 0, 0).timestamp())
    end = int(datetime(2025, 11, 4, 17, 0, 0).timestamp())

    print("Running backtest...")
    print()

    try:
        result = await backtesting.run_backtesting(
            config,
            start,
            end,
            backtesting_resolution="1h",
            trade_cost=0.0  # Use connector fees
        )

        print("✅ Backtest completed!")
        print()

        # Analyze results
        results_dict = result.results
        num_pairs = results_dict['total_executors'] // 2

        print(f"Net PNL: ${results_dict['net_pnl_quote']:.2f}")
        print(f"Total Executors: {results_dict['total_executors']}")
        print(f"Total Pairs: {num_pairs}")
        print()

        # Get token breakdown
        executors_df = result.executors_df
        if not executors_df.empty and 'config' in executors_df.columns:
            executors_df['token'] = executors_df['config'].apply(
                lambda x: x.get('trading_pair', '').split('-')[0]
            )

            print("="*80)
            print("RESULTS")
            print("="*80)
            print()

            print(f"Net PNL: ${results_dict['net_pnl_quote']:.2f}")
            print(f"Total Pairs: {num_pairs}")
            print(f"Unique Tokens: {executors_df['token'].nunique()}")
            print()

            print("TOKENS TRADED:")
            print("="*80)
            token_summary = executors_df.groupby('token').agg({
                'net_pnl_quote': ['count', 'sum']
            }).round(4)
            print(token_summary.to_string())
            print()

            if executors_df['token'].nunique() > 0:
                tokens_list = sorted(executors_df['token'].unique())
                print(f"✅ SUCCESS: Other tokens DID trade without ZEC!")
                print(f"   Tokens: {', '.join(tokens_list)}")
                print()
                print("CONCLUSION: The one-position-per-token limit is blocking opportunities.")
                print("Fix: Remove the limit to allow concurrent positions across tokens.")
            else:
                print("❌ No tokens traded even without ZEC")
                print("This suggests a different issue (data availability, spread calculation, etc.)")
        else:
            print("❌ No trades executed")
            print("   This is unexpected - IP and KAITO should have opportunities")

        print()

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
