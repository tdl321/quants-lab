import logging
import os
from typing import Dict, Optional

import pandas as pd

from core.data_structures.backtesting_result import BacktestingResult
from core.data_paths import data_paths
from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from hummingbot.strategy_v2.controllers import ControllerConfigBase

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BacktestingEngine:
    def __init__(self, load_cached_data: bool = True, custom_backtester: Optional[BacktestingEngineBase] = None):
        self._bt_engine = custom_backtester if custom_backtester is not None else BacktestingEngineBase()
        if load_cached_data:
            self._load_candles_cache()
            self._load_funding_cache()
            self._generate_synthetic_candles()  # Generate synthetic candles for mock connectors
            self._register_mock_connectors()

    def _load_candles_cache(self):
        # Use centralized data paths
        candles_path = data_paths.candles_dir
        if not candles_path.exists():
            logger.warning(f"Candles directory {candles_path} does not exist.")
            return
        all_files = os.listdir(candles_path)
        for file in all_files:
            if file == ".gitignore":
                continue
            try:
                connector_name, trading_pair, interval = file.split(".")[0].split("|")
                candles = pd.read_parquet(candles_path / file)
                candles.index = pd.to_datetime(candles.timestamp, unit='s')
                candles.index.name = None
                columns = ['open', 'high', 'low', 'close', 'volume', 'quote_asset_volume',
                           'n_trades', 'taker_buy_base_volume', 'taker_buy_quote_volume']
                for column in columns:
                    candles[column] = pd.to_numeric(candles[column])
                self._bt_engine.backtesting_data_provider.candles_feeds[
                    f"{connector_name}_{trading_pair}_{interval}"] = candles
                # TODO: evaluate start and end time for each feed
                start_time = candles["timestamp"].min()
                end_time = candles["timestamp"].max()
                self._bt_engine.backtesting_data_provider.start_time = start_time
                self._bt_engine.backtesting_data_provider.end_time = end_time
            except Exception as e:
                logger.error(f"Error loading {file}: {e}")

    def _load_funding_cache(self):
        """Load funding rate data from parquet files."""
        # Use centralized data paths - load from clean directory
        funding_path = data_paths.base_path / 'app' / 'data' / 'cache' / 'funding' / 'clean'

        if not funding_path.exists():
            logger.warning(f"Funding directory {funding_path} does not exist.")
            return

        # Call data provider's loader
        self._bt_engine.backtesting_data_provider.load_funding_rate_data(funding_path)
        logger.info("✅ Funding cache loaded successfully")

    def _generate_synthetic_candles(self):
        """
        Generate synthetic candles data for tokens that don't have historical candles.

        Uses reasonable price estimates for common tokens.
        """
        # Approximate token prices (USD)
        token_prices = {
            "KAITO": 0.50,
            "IP": 1.20,
            "GRASS": 0.80,
            "ZEC": 35.00,
            "APT": 8.50,
            "SUI": 1.50,
            "TRUMP": 3.00,
            "LDO": 2.00,
            "OP": 1.80,
            "SEI": 0.40,
        }

        data_provider = self._bt_engine.backtesting_data_provider

        # Generate candles for both connectors
        for connector in ["extended_perpetual", "lighter_perpetual"]:
            for token, price in token_prices.items():
                trading_pair = f"{token}-USD"
                feed_key = f"{connector}_{trading_pair}_1h"

                # Create synthetic hourly candles covering the data range
                # Use funding data timestamps as reference
                funding_key = f"{connector}_{trading_pair}"
                if funding_key not in data_provider.funding_feeds:
                    continue

                funding_df = data_provider.funding_feeds[funding_key]
                timestamps = funding_df['timestamp'].values

                # Generate candles with small random variation around base price
                import numpy as np
                candles_data = {
                    'timestamp': timestamps,
                    'open': price * (1 + np.random.uniform(-0.01, 0.01, len(timestamps))),
                    'high': price * (1 + np.random.uniform(0, 0.02, len(timestamps))),
                    'low': price * (1 + np.random.uniform(-0.02, 0, len(timestamps))),
                    'close': price * (1 + np.random.uniform(-0.01, 0.01, len(timestamps))),
                    'volume': 1000000,  # Dummy volume
                    'quote_asset_volume': 1000000 * price,
                    'n_trades': 1000,
                    'taker_buy_base_volume': 500000,
                    'taker_buy_quote_volume': 500000 * price,
                }

                candles = pd.DataFrame(candles_data)
                # Set timestamp as index for efficient lookups
                candles.index = pd.to_datetime(candles.timestamp, unit='s')
                candles.index.name = None
                # Also ensure timestamp column remains as unix timestamp for compatibility
                candles['timestamp'] = timestamps

                data_provider.candles_feeds[feed_key] = candles
                logger.debug(f"Generated {len(candles)} candles for {feed_key}")

        logger.info(f"✅ Generated synthetic candles for {len(token_prices)} tokens across 2 connectors")

    def _register_mock_connectors(self):
        """
        Register mock perpetual connectors for backtesting.

        These connectors return historical funding data during simulation.
        """
        from core.backtesting.mock_perpetual_connectors import (
            ExtendedPerpetualMockConnector,
            LighterPerpetualMockConnector
        )

        data_provider = self._bt_engine.backtesting_data_provider

        # Create mock connectors
        extended_connector = ExtendedPerpetualMockConnector(data_provider)
        lighter_connector = LighterPerpetualMockConnector(data_provider)

        # Register in data provider's connectors dict
        # This allows strategy to access them
        data_provider.connectors["extended_perpetual"] = extended_connector
        data_provider.connectors["lighter_perpetual"] = lighter_connector

        logger.info("✅ Registered mock perpetual connectors: extended_perpetual, lighter_perpetual")

    def load_candles_cache_by_connector_pair(self, connector_name: str, trading_pair: str):
            # Use centralized data paths
            candles_path = data_paths.candles_dir
            if not candles_path.exists():
                logger.warning(f"Candles directory {candles_path} does not exist.")
                return
            all_files = os.listdir(candles_path)
            for file in all_files:
                if file == ".gitignore":
                    continue
                try:
                    if connector_name in file and trading_pair in file:
                        connector_name, trading_pair, interval = file.split(".")[0].split("|")
                        candles = pd.read_parquet(candles_path / file)
                        candles.index = pd.to_datetime(candles.timestamp, unit='s')
                        candles.index.name = None
                        columns = ['open', 'high', 'low', 'close', 'volume', 'quote_asset_volume',
                                   'n_trades', 'taker_buy_base_volume', 'taker_buy_quote_volume']
                        for column in columns:
                            candles[column] = pd.to_numeric(candles[column])
                        self._bt_engine.backtesting_data_provider.candles_feeds[
                            f"{connector_name}_{trading_pair}_{interval}"] = candles
                except Exception as e:
                    logger.error(f"Error loading {file}: {e}")

    def get_controller_config_instance_from_dict(self, config: Dict):
        return BacktestingEngineBase.get_controller_config_instance_from_dict(
            config_data=config,
            controllers_module="controllers",
        )

    async def run_backtesting(self, config: ControllerConfigBase, start: int,
                              end: int, backtesting_resolution: str, trade_cost: float = 0.0006) -> BacktestingResult:
        bt_result = await self._bt_engine.run_backtesting(config, start, end, backtesting_resolution, trade_cost)
        return BacktestingResult(bt_result, config)

    async def backtest_controller_from_yml(self,
                                           config_file: str,
                                           controllers_conf_dir_path: str,
                                           start: int,
                                           end: int,
                                           backtesting_resolution: str = "1m",
                                           trade_cost: float = 0.0006,
                                           backtester: Optional[BacktestingEngineBase] = None):
        config = self._bt_engine.get_controller_config_instance_from_yml(config_file, controllers_conf_dir_path)
        return await self.run_backtesting(config, start, end, backtesting_resolution, trade_cost, backtester)
