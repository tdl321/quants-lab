"""
Test Different Spread Thresholds to Maximize Opportunities

Keep everything the same except min_spread to find optimal threshold
that captures more tokens without sacrificing quality.

Usage:
    python scripts/test_spread_thresholds.py
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal
import pandas as pd

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


# Test different spread thresholds
THRESHOLDS_TO_TEST = [
    Decimal('0.003'),   # 0.30% (current - baseline)
    Decimal('0.0025'),  # 0.25%
    Decimal('0.002'),   # 0.20%
    Decimal('0.0015'),  # 0.15%
    Decimal('0.001'),   # 0.10%
    Decimal('0.0005'),  # 0.05%
]


async def run_test(min_spread: Decimal, test_num: int, total_tests: int) -> dict:
    """Run backtest with specific spread threshold."""

    print(f"\n{'='*80}")
    print(f"TEST {test_num}/{total_tests}: Min Spread = {min_spread:.4%}")
    print(f"{'='*80}")

    try:
        # Initialize engine
        custom_engine = MultiConnectorBacktestingEngine()
        backtesting = BacktestingEngine(
            load_cached_data=True,
            custom_backtester=custom_engine
        )

        # Configure controller
        config = FundingRateArbControllerConfig(
            controller_name="funding_rate_arb",
            connector_name="extended_perpetual",
            trading_pair="KAITO-USD",

            connectors={"extended_perpetual", "lighter_perpetual"},
            tokens={"KAITO", "IP", "GRASS", "ZEC", "APT", "SUI", "TRUMP", "LDO", "OP", "SEI"},

            # ONLY CHANGE: min_funding_rate_profitability
            leverage=5,
            min_funding_rate_profitability=min_spread,
            position_size_quote=Decimal('500'),

            # Dynamic exit threshold (proportional to entry)
            absolute_min_spread_exit=min_spread * Decimal('0.67'),
            compression_exit_threshold=Decimal('0.4'),
            max_position_duration_hours=24,
            max_loss_per_position_pct=Decimal('0.03'),

            execution_delay_seconds=120,
        )

        # Backtest period
        start = int(datetime(2025, 10, 4, 20, 0, 0).timestamp())
        end = int(datetime(2025, 11, 4, 17, 0, 0).timestamp())

        # Run with actual connector fees
        result = await backtesting.run_backtesting(
            config,
            start,
            end,
            backtesting_resolution="1h",
            trade_cost=0.0  # Use connector fees
        )

        results_dict = result.results
        num_pairs = results_dict['total_executors'] // 2

        # Get token breakdown
        executors_df = result.executors_df
        executors_df['token'] = executors_df['config'].apply(
            lambda x: x.get('trading_pair', '').split('-')[0]
        )
        unique_tokens = executors_df['token'].nunique()
        tokens_traded = sorted(executors_df['token'].unique())

        # Calculate metrics
        pnl_per_pair = results_dict['net_pnl_quote'] / num_pairs if num_pairs > 0 else 0
        pnl_per_day = results_dict['net_pnl_quote'] / 31

        summary = {
            'min_spread': float(min_spread),
            'net_pnl': float(results_dict['net_pnl_quote']),
            'net_pnl_pct': float(results_dict['net_pnl']),
            'pnl_per_pair': float(pnl_per_pair),
            'pnl_per_day': float(pnl_per_day),
            'total_pairs': num_pairs,
            'total_executors': results_dict['total_executors'],
            'unique_tokens': unique_tokens,
            'tokens_traded': ', '.join(tokens_traded),
            'sharpe_ratio': float(results_dict['sharpe_ratio']),
            'profit_factor': float(results_dict['profit_factor']),
            'max_drawdown': float(results_dict['max_drawdown_usd']),
            'total_volume': float(results_dict['total_volume']),
        }

        print(f"\n✅ Results:")
        print(f"   Net PNL: ${summary['net_pnl']:.2f}")
        print(f"   Pairs: {summary['total_pairs']}")
        print(f"   Tokens: {summary['unique_tokens']} - {summary['tokens_traded']}")
        print(f"   PNL/Pair: ${summary['pnl_per_pair']:.4f}")
        print(f"   Sharpe: {summary['sharpe_ratio']:.2f}")

        return summary

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return {
            'min_spread': float(min_spread),
            'error': str(e)
        }


async def main():
    print()
    print("="*80)
    print("SPREAD THRESHOLD OPTIMIZATION")
    print("="*80)
    print()
    print("Testing different minimum spread thresholds to find optimal")
    print("opportunity capture while maintaining profitability.")
    print()
    print(f"Testing {len(THRESHOLDS_TO_TEST)} thresholds...")
    print()

    results = []

    for i, threshold in enumerate(THRESHOLDS_TO_TEST, 1):
        result = await run_test(threshold, i, len(THRESHOLDS_TO_TEST))
        results.append(result)

    print()
    print("="*80)
    print("SUMMARY")
    print("="*80)
    print()

    # Create DataFrame
    df = pd.DataFrame(results)

    # Save results
    output_file = project_root / "spread_threshold_analysis.csv"
    df.to_csv(output_file, index=False)
    print(f"✅ Results saved to: {output_file}\n")

    # Display comparison
    if 'net_pnl' in df.columns:
        print("THRESHOLD COMPARISON:")
        print("="*80)
        display_df = df[[
            'min_spread', 'net_pnl', 'pnl_per_pair', 'total_pairs',
            'unique_tokens', 'sharpe_ratio'
        ]].copy()

        # Format for display
        display_df['min_spread'] = display_df['min_spread'].apply(lambda x: f"{x:.4%}")

        print(display_df.to_string(index=False))
        print()

        # Find optimal
        best_idx = df['net_pnl'].idxmax()
        best = df.loc[best_idx]

        print("🏆 BEST THRESHOLD:")
        print("="*80)
        print(f"Min Spread: {best['min_spread']:.4%}")
        print(f"Net PNL: ${best['net_pnl']:.2f}")
        print(f"Total Pairs: {best['total_pairs']:.0f}")
        print(f"Unique Tokens: {best['unique_tokens']:.0f}")
        print(f"Tokens: {best['tokens_traded']}")
        print(f"PNL per Pair: ${best['pnl_per_pair']:.4f}")
        print(f"PNL per Day: ${best['pnl_per_day']:.2f}")
        print(f"Sharpe Ratio: {best['sharpe_ratio']:.2f}")
        print()

        # Analysis
        print("ANALYSIS:")
        print("="*80)

        # Show trend
        print("\nPNL vs Threshold:")
        for _, row in df[['min_spread', 'net_pnl', 'total_pairs']].iterrows():
            if 'error' not in row:
                bar_len = int(abs(row['net_pnl']) / 5) if pd.notna(row['net_pnl']) else 0
                bar = '+' * bar_len if row['net_pnl'] > 0 else '-' * bar_len
                print(f"  {row['min_spread']:.4%}: ${row['net_pnl']:>7.2f} {bar} ({row['total_pairs']:.0f} pairs)")

        print()


if __name__ == "__main__":
    asyncio.run(main())
