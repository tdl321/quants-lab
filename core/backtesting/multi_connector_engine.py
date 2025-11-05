"""
Multi-Connector Backtesting Engine

This module provides a specialized backtesting engine for strategies that
trade across multiple connectors simultaneously (e.g., funding rate arbitrage).

The key enhancement is proper price updates for ALL connector/token combinations,
not just the primary connector/pair. This prevents price fallback issues that
cause executor creation failures.

Author: TDL
Date: 2025-11-05
"""

import logging
from decimal import Decimal

from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase

logger = logging.getLogger(__name__)


class MultiConnectorBacktestingEngine(BacktestingEngineBase):
    """
    Enhanced backtesting engine for multi-connector strategies.

    Key Features:
    - Updates prices for ALL connector/token combinations at each timestamp
    - Prevents price fallback to Decimal("1") for non-primary pairs
    - Maintains time-aware data access (no lookahead bias)
    - Compatible with existing controller implementations

    Usage:
        # Create custom engine
        custom_engine = MultiConnectorBacktestingEngine()

        # Pass to BacktestingEngine
        backtesting = BacktestingEngine(
            load_cached_data=True,
            custom_backtester=custom_engine
        )

        # Run backtest as normal
        result = await backtesting.run_backtesting(config, start, end, "1h")
    """

    async def update_state(self, row):
        """
        Update backtesting state with prices for ALL connector/token combinations.

        Standard BacktestingEngineBase only updates one connector/pair:
            key = f"{self.controller.config.connector_name}_{self.controller.config.trading_pair}"
            self.controller.market_data_provider.prices = {key: Decimal(row["close_bt"])}

        This causes multi-connector strategies to get Decimal("1") fallback prices
        for all other pairs, leading to incorrect position sizing and executor failures.

        Our enhancement loops through ALL connectors and tokens to update prices
        from candles feeds, ensuring accurate pricing throughout the backtest.

        Args:
            row: DataFrame row with timestamp and OHLCV data for primary pair
        """
        import pandas as pd

        timestamp = row["timestamp"]
        # Convert timestamp to datetime for index comparison
        timestamp_dt = pd.to_datetime(timestamp, unit='s')

        # Initialize prices dict (will be populated for all pairs)
        prices = {}

        # Get controller config to access connectors and tokens
        config = self.controller.config

        # Update prices for ALL connector/token combinations
        for connector in config.connectors:
            for token in config.tokens:
                trading_pair = f"{token}-USD"
                price_key = f"{connector}_{trading_pair}"
                candles_key = f"{price_key}_1h"

                # Get candles feed for this connector/pair
                candles_df = self.controller.market_data_provider.candles_feeds.get(candles_key)

                if candles_df is not None:
                    # Try to get price at exact timestamp
                    if timestamp_dt in candles_df.index:
                        price = candles_df.loc[timestamp_dt, 'close']
                        prices[price_key] = Decimal(str(price))
                        logger.debug(f"Updated price for {price_key}: {price} at {timestamp}")
                    else:
                        # Timestamp not in index - try to find nearest price
                        # This handles potential timestamp misalignment
                        candles_before = candles_df[candles_df.index <= timestamp_dt]
                        if not candles_before.empty:
                            latest_candle = candles_before.iloc[-1]
                            price = latest_candle['close']
                            prices[price_key] = Decimal(str(price))
                            logger.debug(f"Using nearest price for {price_key}: {price} (from {latest_candle.name})")
                        else:
                            logger.warning(f"No price data available for {price_key} at or before {timestamp}")
                else:
                    logger.warning(f"No candles feed found for {candles_key}")

        # Update market data provider with all prices
        self.controller.market_data_provider.prices = prices

        # Update current timestamp (maintains time-awareness)
        self.controller.market_data_provider._time = timestamp

        # Update controller's processed data with current row
        self.controller.processed_data.update(row.to_dict())

        # Update executors info (check for TP/SL hits, etc.)
        self.update_executors_info(timestamp)

        # Log summary of price updates every 24 hours (to avoid spam)
        if hasattr(self, '_last_log_timestamp'):
            hours_since_log = (timestamp - self._last_log_timestamp) / 3600
            if hours_since_log >= 24:
                logger.info(f"Price update checkpoint: {len(prices)} prices updated at {timestamp}")
                logger.info(f"Sample prices: {dict(list(prices.items())[:3])}")
                self._last_log_timestamp = timestamp
        else:
            # First update - log it
            logger.info(f"Initial price update: {len(prices)} prices set at timestamp {timestamp}")
            logger.info(f"Sample prices: {dict(list(prices.items())[:3])}")
            self._last_log_timestamp = timestamp
