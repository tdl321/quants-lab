"""
Funding Rate Backtest Data Provider

Provides historical funding rate data to backtesting engine in a time-series format.
Enables strategy to query funding rates at specific timestamps for simulation.

Author: TDL
Date: 2025-11-04
Reference: FUNDING_RATE_ARB_BACKTEST_PLAN.md - Component 3
"""

import logging
from pathlib import Path
from typing import Optional, Tuple, List, Dict
import pandas as pd
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FundingRateBacktestDataProvider:
    """
    Provides historical funding rate data for backtesting.

    This class loads funding rate data from parquet files and provides
    time-based access for backtesting the funding rate arbitrage strategy.

    Usage:
        >>> provider = FundingRateBacktestDataProvider()
        >>> provider.load_data(start_date="2025-11-01", end_date="2025-11-04")
        >>> rate = provider.get_funding_rate(timestamp, "lighter", "KAITO")
        >>> spread = provider.get_spread(timestamp, "lighter", "extended", "KAITO")
    """

    DEFAULT_DATA_PATH = "/Users/tdl321/quants-lab/app/data/cache/funding/raw"

    def __init__(self, data_path: Optional[str] = None):
        """
        Initialize the backtest data provider.

        Args:
            data_path: Path to directory containing parquet files
                      (default: quants-lab/app/data/cache/funding/raw)
        """
        self.data_path = Path(data_path or self.DEFAULT_DATA_PATH)
        self.data: Optional[pd.DataFrame] = None
        self.exchanges: List[str] = []
        self.tokens: List[str] = []
        self.start_timestamp: Optional[int] = None
        self.end_timestamp: Optional[int] = None

        logger.info(f"FundingRateBacktestDataProvider initialized")
        logger.info(f"  Data path: {self.data_path}")

    def load_data(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Load historical funding rate data from parquet files.

        Args:
            start_date: Start date in 'YYYY-MM-DD' format (None = all data)
            end_date: End date in 'YYYY-MM-DD' format (None = all data)

        Returns:
            DataFrame with loaded funding rate data

        Raises:
            FileNotFoundError: If no data files found
        """
        logger.info("Loading funding rate data for backtest...")

        # Get all parquet files
        parquet_files = sorted(self.data_path.glob("*.parquet"))

        if not parquet_files:
            raise FileNotFoundError(f"No data files found in {self.data_path}")

        # Filter by date range if specified
        if start_date:
            parquet_files = [f for f in parquet_files if f.stem >= start_date]

        if end_date:
            parquet_files = [f for f in parquet_files if f.stem <= end_date]

        if not parquet_files:
            raise ValueError(f"No data found in range {start_date} to {end_date}")

        # Load and combine all files
        dfs = []
        for file in parquet_files:
            df = pd.read_parquet(file)
            dfs.append(df)

        self.data = pd.concat(dfs, ignore_index=True)

        # Sort by timestamp
        self.data = self.data.sort_values('timestamp').reset_index(drop=True)

        # Extract metadata
        self.exchanges = sorted(self.data['exchange'].unique().tolist())
        self.tokens = sorted(self.data['base'].unique().tolist())
        self.start_timestamp = int(self.data['timestamp'].min())
        self.end_timestamp = int(self.data['timestamp'].max())

        logger.info(f"✅ Loaded {len(self.data)} records")
        logger.info(f"  Date range: {datetime.fromtimestamp(self.start_timestamp)} to {datetime.fromtimestamp(self.end_timestamp)}")
        logger.info(f"  Exchanges: {', '.join(self.exchanges)}")
        logger.info(f"  Tokens: {', '.join(self.tokens)}")

        return self.data

    def get_funding_rate(
        self,
        timestamp: int,
        exchange: str,
        token: str
    ) -> Optional[float]:
        """
        Get funding rate at specific timestamp for exchange and token.

        Uses the most recent funding rate data available at or before the timestamp.

        Args:
            timestamp: Unix timestamp
            exchange: Exchange ID (e.g., "lighter", "extended")
            token: Token symbol (e.g., "KAITO")

        Returns:
            Funding rate as float, or None if not available
        """
        if self.data is None:
            raise RuntimeError("Data not loaded. Call load_data() first.")

        # Filter for specific exchange and token
        mask = (
            (self.data['exchange'] == exchange) &
            (self.data['base'] == token) &
            (self.data['timestamp'] <= timestamp)
        )

        matching_data = self.data[mask]

        if matching_data.empty:
            return None

        # Get most recent rate
        latest_row = matching_data.iloc[-1]
        return float(latest_row['funding_rate'])

    def get_spread(
        self,
        timestamp: int,
        exchange1: str,
        exchange2: str,
        token: str
    ) -> Optional[float]:
        """
        Calculate funding rate spread between two exchanges at timestamp.

        Args:
            timestamp: Unix timestamp
            exchange1: First exchange ID
            exchange2: Second exchange ID
            token: Token symbol

        Returns:
            Absolute spread (|rate1 - rate2|), or None if data unavailable
        """
        rate1 = self.get_funding_rate(timestamp, exchange1, token)
        rate2 = self.get_funding_rate(timestamp, exchange2, token)

        if rate1 is None or rate2 is None:
            return None

        return abs(rate1 - rate2)

    def get_best_spread(
        self,
        timestamp: int,
        token: str
    ) -> Optional[Tuple[str, str, float]]:
        """
        Find the best (largest) funding rate spread for a token across all exchanges.

        Args:
            timestamp: Unix timestamp
            token: Token symbol

        Returns:
            Tuple of (exchange1, exchange2, spread) or None if insufficient data
        """
        if self.data is None:
            raise RuntimeError("Data not loaded. Call load_data() first.")

        # Get rates from all exchanges for this token
        rates = {}
        for exchange in self.exchanges:
            rate = self.get_funding_rate(timestamp, exchange, token)
            if rate is not None:
                rates[exchange] = rate

        if len(rates) < 2:
            return None

        # Find max spread
        max_spread = 0
        best_pair = (None, None)

        exchanges_list = list(rates.keys())
        for i, ex1 in enumerate(exchanges_list):
            for ex2 in exchanges_list[i+1:]:
                spread = abs(rates[ex1] - rates[ex2])
                if spread > max_spread:
                    max_spread = spread
                    best_pair = (ex1, ex2)

        if best_pair[0] is None:
            return None

        return (best_pair[0], best_pair[1], max_spread)

    def get_funding_payment_times(
        self,
        exchange: str,
        interval_hours: int = 1
    ) -> List[int]:
        """
        Get timestamps when funding payments occur on an exchange.

        For most perp DEXs, funding is paid hourly.

        Args:
            exchange: Exchange ID
            interval_hours: Hours between funding payments (default: 1)

        Returns:
            List of funding payment timestamps within loaded data range
        """
        if self.data is None:
            raise RuntimeError("Data not loaded. Call load_data() first.")

        # Get all unique timestamps for this exchange
        exchange_data = self.data[self.data['exchange'] == exchange]

        if exchange_data.empty:
            return []

        # Funding payments typically happen at the hour mark
        # Return all timestamps in the data (they represent funding payment times)
        payment_times = sorted(exchange_data['timestamp'].unique().tolist())

        return payment_times

    def interpolate_missing_data(self) -> pd.DataFrame:
        """
        Interpolate missing funding rate data for continuity.

        This forward-fills funding rates within reasonable time gaps
        to ensure backtesting can run continuously.

        Returns:
            DataFrame with interpolated data
        """
        if self.data is None:
            raise RuntimeError("Data not loaded. Call load_data() first.")

        logger.info("Interpolating missing funding rate data...")

        # Create a complete time index
        all_timestamps = self.data['timestamp'].unique()

        interpolated_dfs = []

        for exchange in self.exchanges:
            for token in self.tokens:
                # Get data for this exchange-token pair
                mask = (
                    (self.data['exchange'] == exchange) &
                    (self.data['base'] == token)
                )
                pair_data = self.data[mask].copy()

                if pair_data.empty:
                    continue

                # Reindex to all timestamps and forward fill
                pair_data = pair_data.set_index('timestamp')
                pair_data = pair_data.reindex(all_timestamps)
                pair_data['exchange'] = exchange
                pair_data['base'] = token

                # Forward fill funding rate (max 2 hours)
                pair_data['funding_rate'] = pair_data['funding_rate'].fillna(method='ffill', limit=2)

                # Reset index
                pair_data = pair_data.reset_index()
                pair_data = pair_data.rename(columns={'index': 'timestamp'})

                # Drop rows still missing data
                pair_data = pair_data.dropna(subset=['funding_rate'])

                interpolated_dfs.append(pair_data)

        if not interpolated_dfs:
            logger.warning("No data to interpolate")
            return self.data

        interpolated_data = pd.concat(interpolated_dfs, ignore_index=True)
        interpolated_data = interpolated_data.sort_values('timestamp').reset_index(drop=True)

        logger.info(f"✅ Interpolated {len(interpolated_data)} records (from {len(self.data)})")

        return interpolated_data

    def get_data_summary(self) -> Dict:
        """
        Get summary statistics of loaded data.

        Returns:
            Dict with data coverage, gaps, and quality metrics
        """
        if self.data is None:
            raise RuntimeError("Data not loaded. Call load_data() first.")

        # Calculate coverage per exchange-token pair
        coverage = []
        for exchange in self.exchanges:
            for token in self.tokens:
                mask = (
                    (self.data['exchange'] == exchange) &
                    (self.data['base'] == token)
                )
                count = mask.sum()
                if count > 0:
                    coverage.append({
                        'exchange': exchange,
                        'token': token,
                        'snapshots': count
                    })

        # Find time gaps
        timestamps = sorted(self.data['timestamp'].unique())
        gaps = []
        if len(timestamps) > 1:
            for i in range(len(timestamps) - 1):
                gap_hours = (timestamps[i+1] - timestamps[i]) / 3600
                if gap_hours > 2:  # Gaps larger than 2 hours
                    gaps.append({
                        'from': datetime.fromtimestamp(timestamps[i]),
                        'to': datetime.fromtimestamp(timestamps[i+1]),
                        'hours': gap_hours
                    })

        summary = {
            'total_records': len(self.data),
            'exchanges': self.exchanges,
            'tokens': self.tokens,
            'start_time': datetime.fromtimestamp(self.start_timestamp),
            'end_time': datetime.fromtimestamp(self.end_timestamp),
            'duration_hours': (self.end_timestamp - self.start_timestamp) / 3600,
            'unique_timestamps': len(timestamps),
            'coverage_by_pair': coverage,
            'time_gaps': gaps,
            'completeness': len(coverage) / (len(self.exchanges) * len(self.tokens))
        }

        return summary
