"""
Run Funding Rate Arbitrage Backtest (Controller-based)

Uses cleaned historical funding data from Extended and Lighter DEXs.
No Jupyter notebook required - pure Python CLI script.

Data Timing:
- Funding rates = historical payments (past data)
- 2-minute execution delay for data propagation
- No lookahead bias

Usage:
    python scripts/run_funding_arb_backtest_controller.py
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal
import pandas as pd

# Add paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.backtesting import BacktestingEngine
from controllers.funding_rate_arb import FundingRateArbControllerConfig


async def main():
    print()
    print("="*80)
    print("FUNDING RATE ARBITRAGE BACKTEST (Controller-based)")
    print("="*80)
    print()

    # Step 1: Initialize backtesting engine
    print("Step 1: Initializing backtesting engine...")
    try:
        # Load cached data (including your cleaned funding data)
        backtesting = BacktestingEngine(load_cached_data=True)

        # Verify funding data loaded
        data_provider = backtesting._bt_engine.backtesting_data_provider
        print(f"✅ Engine initialized")
        print(f"   Funding feeds: {len(data_provider.funding_feeds)}")
        connectors_list = list(data_provider.connectors.keys())[:5]
        print(f"   Connectors: {connectors_list}")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        import traceback
        traceback.print_exc()
        return False

    print()

    # Step 2: Configure controller
    print("Step 2: Configuring funding rate arbitrage controller...")
    try:
        config = FundingRateArbControllerConfig(
            controller_name="funding_rate_arb",
            connector_name="extended_perpetual",
            trading_pair="KAITO-USD",

            # Multi-connector arbitrage
            connectors={"extended_perpetual", "lighter_perpetual"},
            tokens={"KAITO", "IP", "GRASS", "ZEC", "APT", "SUI", "TRUMP", "LDO", "OP", "SEI"},

            # Strategy parameters
            leverage=5,
            min_funding_rate_profitability=Decimal('0.003'),  # 0.3% hourly
            position_size_quote=Decimal('500'),  # $500 per side

            # Exit conditions
            absolute_min_spread_exit=Decimal('0.002'),  # 0.2%
            compression_exit_threshold=Decimal('0.4'),  # 60% compression
            max_position_duration_hours=24,
            max_loss_per_position_pct=Decimal('0.03'),  # 3% stop loss

            # Timing safeguard: 2-minute execution delay
            execution_delay_seconds=120,
        )

        print("✅ Controller configured:")
        print(f"   Connectors: {', '.join(config.connectors)}")
        print(f"   Tokens: {len(config.tokens)}")
        print(f"   Min spread: {config.min_funding_rate_profitability:.2%}")
        print(f"   Position size: ${config.position_size_quote} per side")
        print(f"   Leverage: {config.leverage}x")
        print(f"   Execution delay: {config.execution_delay_seconds}s")
    except Exception as e:
        print(f"❌ Failed to configure: {e}")
        import traceback
        traceback.print_exc()
        return False

    print()

    # Step 3: Set backtest period
    print("Step 3: Setting backtest period...")
    # Match your cleaned data range: Oct 4 20:00 to Nov 4 17:00
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
        # Get executors
        executors_info = backtesting_result['executors']

        if not executors_info:
            print("⚠️  No positions opened during backtest")
            print()
            print("Possible reasons:")
            print("- Funding rate spreads never exceeded minimum threshold")
            print("- Check min_funding_rate_profitability setting")
            return False

        # Convert to DataFrame
        executors_df = pd.DataFrame([
            {
                'id': e.id,
                'timestamp': e.timestamp,
                'trading_pair': e.config.trading_pair,
                'connector': e.config.connector_name,
                'side': e.config.side.name,
                'amount': float(e.config.amount),
                'net_pnl_quote': float(e.net_pnl_quote),
                'net_pnl_pct': float(e.net_pnl_pct),
                'close_timestamp': e.close_timestamp,
                'status': e.status.name
            }
            for e in executors_info
        ])

        # Calculate metrics
        total_positions = len(executors_df) // 2  # Divide by 2 (paired positions)
        profitable = (executors_df['net_pnl_quote'] > 0).sum()
        losing = (executors_df['net_pnl_quote'] < 0).sum()

        total_pnl = executors_df['net_pnl_quote'].sum()
        avg_profit = executors_df[executors_df['net_pnl_quote'] > 0]['net_pnl_quote'].mean() if profitable > 0 else 0
        avg_loss = executors_df[executors_df['net_pnl_quote'] < 0]['net_pnl_quote'].mean() if losing > 0 else 0

        print(f"Total Arbitrage Positions: {total_positions} (paired long+short)")
        print(f"Total Executors: {len(executors_df)}")
        print(f"Profitable Sides: {profitable}")
        print(f"Losing Sides: {losing}")
        print()
        print(f"Total PNL: ${total_pnl:.2f}")
        print(f"Average Profit: ${avg_profit:.2f}")
        print(f"Average Loss: ${avg_loss:.2f}")
        print()

        # Performance by token
        print("Performance by Token:")
        print("-" * 80)
        executors_df['token'] = executors_df['trading_pair'].str.split('-').str[0]
        token_perf = executors_df.groupby('token').agg({
            'net_pnl_quote': ['sum', 'mean', 'count']
        }).round(2)
        token_perf.columns = ['Total PNL', 'Avg PNL', 'Executions']
        token_perf = token_perf.sort_values('Total PNL', ascending=False)
        print(token_perf.to_string())
        print()

        # Performance by connector
        print("Performance by Connector:")
        print("-" * 80)
        connector_perf = executors_df.groupby('connector').agg({
            'net_pnl_quote': ['sum', 'mean', 'count']
        }).round(2)
        connector_perf.columns = ['Total PNL', 'Avg PNL', 'Executions']
        print(connector_perf.to_string())
        print()

        # Save results
        output_path = project_root / 'backtest_results_funding_arb_controller.csv'
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
