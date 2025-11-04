"""
Funding Rate Data Collector

Automated collection and storage of historical funding rate data from any data source.
Used for backtesting the funding rate arbitrage strategy.

Author: TDL
Date: 2025-11-04
Reference: FUNDING_RATE_ARB_BACKTEST_PLAN.md - Component 2
"""

import asyncio
import logging
import json
import time
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import pandas as pd

from core.data_sources.base_funding_source import BaseFundingDataSource
from core.data_sources.coingecko_funding import CoinGeckoFundingDataSource

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FundingRateCollector:
    """
    Automated collector for funding rate data from any data source.

    Features:
    - Scheduled polling at configurable intervals
    - Data persistence to parquet files
    - Incremental updates (append new snapshots)
    - Spread calculation
    - Data validation
    - Metadata tracking
    - Modular data source support (CoinGecko, Extended, etc.)

    Usage:
        >>> # With CoinGecko (default)
        >>> collector = FundingRateCollector(
        ...     api_key="your-key",
        ...     exchanges=["lighter", "extended"],
        ...     tokens=["KAITO", "IP", "GRASS"]
        ... )
        >>>
        >>> # With custom data source
        >>> from core.data_sources.extended_funding import ExtendedFundingDataSource
        >>> source = ExtendedFundingDataSource()
        >>> collector = FundingRateCollector(
        ...     data_source=source,
        ...     exchanges=["extended"],
        ...     tokens=["KAITO"]
        ... )
        >>> await collector.start_collection(duration_hours=24, interval_minutes=60)
    """

    DEFAULT_STORAGE_PATH = "/Users/tdl321/quants-lab/app/data/cache/funding"

    def __init__(
        self,
        api_key: Optional[str] = None,
        user_agent: str = "backtest",
        exchanges: Optional[List[str]] = None,
        tokens: Optional[List[str]] = None,
        storage_path: Optional[str] = None,
        data_source: Optional[BaseFundingDataSource] = None
    ):
        """
        Initialize the funding rate collector.

        Args:
            api_key: CoinGecko API key (None for free tier) - only used if data_source is None
            user_agent: User agent for API requests - only used if data_source is None
            exchanges: List of exchange IDs to collect from
            tokens: List of tokens to track
            storage_path: Path to store collected data
            data_source: Optional custom data source (defaults to CoinGecko if not provided)
        """
        # Initialize data source (default to CoinGecko for backward compatibility)
        if data_source is not None:
            self.cg_source = data_source
        else:
            self.cg_source = CoinGeckoFundingDataSource(
                api_key=api_key,
                user_agent=user_agent
            )

        # Collection configuration
        self.exchanges = exchanges or ["lighter", "extended"]
        self.tokens = tokens or [
            "KAITO", "IP", "GRASS", "ZEC", "APT", "SUI",
            "TRUMP", "LDO", "OP", "SEI"
        ]

        # Storage configuration
        self.storage_path = Path(storage_path or self.DEFAULT_STORAGE_PATH)
        self.raw_data_path = self.storage_path / "raw"
        self.processed_data_path = self.storage_path / "processed"
        self.metadata_path = self.storage_path / "metadata.json"

        # Ensure directories exist
        self.raw_data_path.mkdir(parents=True, exist_ok=True)
        self.processed_data_path.mkdir(parents=True, exist_ok=True)

        # Collection state
        self.collection_start_time: Optional[float] = None
        self.snapshots_collected: int = 0
        self.is_collecting: bool = False

        logger.info(f"FundingRateCollector initialized")
        logger.info(f"  Exchanges: {', '.join(self.exchanges)}")
        logger.info(f"  Tokens: {', '.join(self.tokens)}")
        logger.info(f"  Storage: {self.storage_path}")

    async def collect_single_snapshot(self) -> Optional[pd.DataFrame]:
        """
        Collect a single snapshot of funding rates from all exchanges.

        Returns:
            DataFrame with funding rates, or None if collection failed
        """
        logger.info("Collecting funding rate snapshot...")

        try:
            # Fetch funding rates from all exchanges
            df = await self.cg_source.get_funding_rates_multi_exchange(
                exchanges=self.exchanges,
                tokens=self.tokens
            )

            if df.empty:
                logger.warning("No funding data collected")
                return None

            logger.info(f"✅ Collected {len(df)} funding rates from {df['exchange'].nunique()} exchanges")
            self.snapshots_collected += 1

            return df

        except Exception as e:
            logger.error(f"Failed to collect snapshot: {e}")
            return None

    def save_snapshot(self, data: pd.DataFrame, append: bool = True):
        """
        Save funding rate snapshot to parquet file.

        Args:
            data: DataFrame with funding rate data
            append: If True, append to existing file; otherwise overwrite
        """
        if data is None or data.empty:
            logger.warning("No data to save")
            return

        # Generate filename based on date
        timestamp = data['timestamp'].iloc[0]
        date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
        filename = self.raw_data_path / f"{date_str}.parquet"

        try:
            if append and filename.exists():
                # Load existing data and append
                existing_df = pd.read_parquet(filename)
                combined_df = pd.concat([existing_df, data], ignore_index=True)

                # Remove duplicates (same timestamp + exchange + base)
                combined_df = combined_df.drop_duplicates(
                    subset=['timestamp', 'exchange', 'base'],
                    keep='last'
                )

                combined_df.to_parquet(filename, index=False)
                logger.info(f"✅ Appended to {filename} ({len(data)} new rows)")
            else:
                # Save new file
                data.to_parquet(filename, index=False)
                logger.info(f"✅ Saved to {filename} ({len(data)} rows)")

        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")

    async def start_collection(
        self,
        duration_hours: Optional[float] = None,
        interval_minutes: int = 60,
        max_snapshots: Optional[int] = None
    ):
        """
        Start automated data collection with scheduled polling.

        Args:
            duration_hours: How long to collect data (None = run indefinitely)
            interval_minutes: Time between snapshots in minutes
            max_snapshots: Maximum number of snapshots to collect (None = unlimited)
        """
        logger.info("=" * 70)
        logger.info("STARTING FUNDING RATE DATA COLLECTION")
        logger.info("=" * 70)
        logger.info(f"Duration: {duration_hours or 'Continuous'} hours")
        logger.info(f"Interval: {interval_minutes} minutes")
        logger.info(f"Max snapshots: {max_snapshots or 'Unlimited'}")
        logger.info("=" * 70)

        self.is_collecting = True
        self.collection_start_time = time.time()
        start_time = self.collection_start_time

        # Calculate end time if duration specified
        end_time = start_time + (duration_hours * 3600) if duration_hours else None

        try:
            # Start CoinGecko session
            await self.cg_source.start()

            snapshot_count = 0

            while self.is_collecting:
                # Collect snapshot
                logger.info(f"\n📸 Snapshot #{snapshot_count + 1}")
                snapshot_data = await self.collect_single_snapshot()

                if snapshot_data is not None:
                    # Save to disk
                    self.save_snapshot(snapshot_data, append=True)
                    snapshot_count += 1

                # Check stopping conditions
                if max_snapshots and snapshot_count >= max_snapshots:
                    logger.info(f"✅ Reached max snapshots ({max_snapshots})")
                    break

                if end_time and time.time() >= end_time:
                    logger.info(f"✅ Reached duration limit ({duration_hours} hours)")
                    break

                # Wait for next interval
                next_collection_time = time.time() + (interval_minutes * 60)
                wait_seconds = next_collection_time - time.time()

                if wait_seconds > 0:
                    logger.info(f"⏳ Waiting {wait_seconds/60:.1f} minutes until next snapshot...")
                    await asyncio.sleep(wait_seconds)

        except KeyboardInterrupt:
            logger.info("\n⚠️  Collection interrupted by user")

        except Exception as e:
            logger.error(f"❌ Collection error: {e}")
            raise

        finally:
            self.is_collecting = False
            await self.cg_source.stop()

            # Update metadata
            self.update_metadata()

            # Print summary
            elapsed_hours = (time.time() - start_time) / 3600
            logger.info("\n" + "=" * 70)
            logger.info("COLLECTION COMPLETE")
            logger.info("=" * 70)
            logger.info(f"Total snapshots: {snapshot_count}")
            logger.info(f"Total duration: {elapsed_hours:.2f} hours")
            logger.info(f"Data stored in: {self.storage_path}")
            logger.info("=" * 70)

    async def stop_collection(self):
        """Stop the collection process."""
        logger.info("Stopping collection...")
        self.is_collecting = False

    def load_historical_data(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Load historical funding rate data from stored parquet files.

        Args:
            start_date: Start date in 'YYYY-MM-DD' format (None = earliest)
            end_date: End date in 'YYYY-MM-DD' format (None = latest)

        Returns:
            DataFrame with historical funding rates
        """
        logger.info("Loading historical data...")

        # Get all parquet files
        parquet_files = sorted(self.raw_data_path.glob("*.parquet"))

        if not parquet_files:
            logger.warning("No historical data found")
            return pd.DataFrame()

        # Filter by date range if specified
        if start_date:
            parquet_files = [f for f in parquet_files if f.stem >= start_date]

        if end_date:
            parquet_files = [f for f in parquet_files if f.stem <= end_date]

        if not parquet_files:
            logger.warning(f"No data found in range {start_date} to {end_date}")
            return pd.DataFrame()

        # Load and combine all files
        dfs = []
        for file in parquet_files:
            df = pd.read_parquet(file)
            dfs.append(df)

        combined_df = pd.concat(dfs, ignore_index=True)

        # Sort by timestamp
        combined_df = combined_df.sort_values('timestamp')

        logger.info(f"✅ Loaded {len(combined_df)} records from {len(parquet_files)} files")

        return combined_df

    def calculate_spreads(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate funding rate spreads between exchanges.

        Args:
            data: DataFrame with funding rates from multiple exchanges

        Returns:
            DataFrame with spread calculations
        """
        return self.cg_source.calculate_spreads(data)

    def validate_data_quality(self, data: pd.DataFrame) -> Dict:
        """
        Validate data quality and return metrics.

        Args:
            data: DataFrame with funding rate data

        Returns:
            Dict with quality metrics
        """
        if data.empty:
            return {"valid": False, "reason": "Empty dataset"}

        metrics = {
            "valid": True,
            "total_records": len(data),
            "exchanges": data['exchange'].nunique(),
            "tokens": data['base'].nunique(),
            "date_range": {
                "start": datetime.fromtimestamp(data['timestamp'].min()).isoformat(),
                "end": datetime.fromtimestamp(data['timestamp'].max()).isoformat()
            },
            "null_funding_rates": data['funding_rate'].isna().sum(),
            "null_prices": data['index'].isna().sum(),
            "completeness": 1.0 - (data.isna().sum().sum() / (len(data) * len(data.columns)))
        }

        return metrics

    def update_metadata(self):
        """Update metadata file with collection information."""
        try:
            metadata = {
                "collection_start": datetime.fromtimestamp(self.collection_start_time).isoformat() if self.collection_start_time else None,
                "collection_end": datetime.now().isoformat(),
                "exchanges": self.exchanges,
                "tokens": self.tokens,
                "total_snapshots": self.snapshots_collected,
                "storage_path": str(self.storage_path)
            }

            with open(self.metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"✅ Metadata updated: {self.metadata_path}")

        except Exception as e:
            logger.error(f"Failed to update metadata: {e}")

    def get_metadata(self) -> Dict:
        """Load and return collection metadata."""
        if self.metadata_path.exists():
            with open(self.metadata_path, 'r') as f:
                return json.load(f)
        return {}
