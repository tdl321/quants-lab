"""
Run Funding Rate Arbitrage Backtest

Backtests the v2_funding_rate_arb strategy on 31 days of historical
Extended and Lighter funding rate data.

Usage:
    python scripts/run_funding_arb_backtest.py
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add paths
project_root = Path(__file__).parent.parent
hummingbot_root = project_root.parent / 'hummingbot'
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(hummingbot_root))

from core.backtesting import BacktestingEngine
from core.data_structures.backtesting_result import BacktestingResult


async def main():
    print()
    print("="*80)
    print("FUNDING RATE ARBITRAGE BACKTEST")
    print("="*80)
    print()

    # Step 1: Initialize backtesting engine
    print("Step 1: Initializing backtesting engine...")
    try:
        backtesting = BacktestingEngine(load_cached_data=True)
        print("✅ Engine initialized")

        # Verify data loaded
        data_provider = backtesting._bt_engine.backtesting_data_provider
        print(f"   Funding feeds: {len(data_provider.funding_feeds)}")
        print(f"   Connectors: {list(data_provider.connectors.keys())}")
    except Exception as e:
        print(f"❌ Failed to initialize engine: {e}")
        import traceback
        traceback.print_exc()
        return False

    print()

    # Step 2: Import and configure strategy
    print("Step 2: Configuring strategy...")
    try:
        # Import strategy config from hummingbot
        sys.path.insert(0, str(hummingbot_root / 'scripts'))
        from v2_funding_rate_arb import FundingRateArbitrageConfig

        config = FundingRateArbitrageConfig(
            connectors={"extended_perpetual", "lighter_perpetual"},
            tokens={"KAITO", "IP", "GRASS", "ZEC", "APT", "SUI", "TRUMP", "LDO", "OP", "SEI"},
            leverage=5,
            min_funding_rate_profitability=Decimal('0.003'),  # 0.3% hourly
            position_size_quote=Decimal('500'),  # $500 per side
            absolute_min_spread_exit=Decimal('0.002'),  # 0.2%
            compression_exit_threshold=Decimal('0.4'),  # 60% compression
            max_position_duration_hours=24,
            max_loss_per_position_pct=Decimal('0.03'),  # 3% stop loss
            trade_profitability_condition_to_enter=False
        )

        print("✅ Strategy configured:")
        print(f"   Exchanges: extended_perpetual, lighter_perpetual")
        print(f"   Tokens: {len(config.tokens)}")
        print(f"   Min spread: {config.min_funding_rate_profitability:.2%}")
        print(f"   Position size: ${config.position_size_quote} per side")
        print(f"   Leverage: {config.leverage}x")
    except Exception as e:
        print(f"❌ Failed to configure strategy: {e}")
        import traceback
        traceback.print_exc()
        return False

    print()

    # Step 3: Set backtest period
    print("Step 3: Setting backtest period...")
    # Use Oct 4 20:00 to Nov 4 17:00 (31 days, avoiding the missing ZEC hour)
    start = int(datetime(2024, 10, 4, 20, 0, 0).timestamp())
    end = int(datetime(2024, 11, 4, 17, 0, 0).timestamp())
    backtesting_resolution = "1h"

    print(f"   Start: {datetime.fromtimestamp(start)}")
    print(f"   End: {datetime.fromtimestamp(end)}")
    print(f"   Duration: {(end - start) / 3600 / 24:.1f} days")
    print(f"   Resolution: {backtesting_resolution}")

    print()

    # Step 4: Run backtest
    print("Step 4: Running backtest...")
    print("   (This may take a few minutes...)")
    print()

    try:
        backtesting_result = await backtesting.run_backtesting(
            config,
            start,
            end,
            backtesting_resolution,
            trade_cost=0.0005  # 0.05% trading fee
        )

        print("✅ Backtest completed successfully!")
        print()

    except Exception as e:
        print(f"❌ Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Step 5: Display results
    print("="*80)
    print("BACKTEST RESULTS")
    print("="*80)
    print()

    try:
        # Get executors dataframe
        executors_df = backtesting_result.executors_df

        if executors_df.empty:
            print("⚠️  No positions opened during backtest")
            print()
            print("Possible reasons:")
            print("- Funding rate spreads never exceeded minimum threshold (0.3%)")
            print("- No arbitrage opportunities detected")
            print("- Data quality issues")
            return False

        # Basic metrics
        total_positions = len(executors_df)
        profitable_positions = (executors_df['net_pnl_quote'] > 0).sum()
        losing_positions = (executors_df['net_pnl_quote'] < 0).sum()
        win_rate = (executors_df['net_pnl_quote'] > 0).mean()

        total_pnl = executors_df['net_pnl_quote'].sum()
        avg_profit = executors_df[executors_df['net_pnl_quote'] > 0]['net_pnl_quote'].mean() if profitable_positions > 0 else 0
        avg_loss = executors_df[executors_df['net_pnl_quote'] < 0]['net_pnl_quote'].mean() if losing_positions > 0 else 0

        print(f"Total Positions: {total_positions}")
        print(f"Profitable: {profitable_positions} ({win_rate:.1%} win rate)")
        print(f"Losing: {losing_positions}")
        print()
        print(f"Total PNL: ${total_pnl:.2f}")
        print(f"Average Profit: ${avg_profit:.2f}")
        print(f"Average Loss: ${avg_loss:.2f}")
        print()

        # Performance by token
        print("Performance by Token:")
        print("-" * 80)
        token_performance = executors_df.groupby('trading_pair').agg({
            'net_pnl_quote': ['sum', 'mean', 'count'],
        }).round(2)
        token_performance.columns = ['Total PNL', 'Avg PNL', 'Count']
        token_performance['Win Rate'] = executors_df.groupby('trading_pair')['net_pnl_quote'].apply(
            lambda x: (x > 0).mean()
        )
        token_performance = token_performance.sort_values('Total PNL', ascending=False)
        print(token_performance.to_string())
        print()

        # Risk metrics
        max_profit = executors_df['net_pnl_quote'].max()
        max_loss = executors_df['net_pnl_quote'].min()

        print("Risk Metrics:")
        print("-" * 80)
        print(f"Max Single Profit: ${max_profit:.2f}")
        print(f"Max Single Loss: ${max_loss:.2f}")
        print(f"Profit Factor: {abs(executors_df[executors_df['net_pnl_quote'] > 0]['net_pnl_quote'].sum() / executors_df[executors_df['net_pnl_quote'] < 0]['net_pnl_quote'].sum()) if losing_positions > 0 else float('inf'):.2f}")
        print()

        # Save results
        output_path = project_root / 'backtest_results_funding_arb.csv'
        executors_df.to_csv(output_path, index=False)
        print(f"✅ Results saved to: {output_path}")
        print()

        return True

    except Exception as e:
        print(f"❌ Error analyzing results: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
