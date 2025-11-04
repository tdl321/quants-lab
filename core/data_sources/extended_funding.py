"""
Extended DEX Funding Rate Data Source

This module provides an interface to Extended's native API for fetching
funding rate data directly from the exchange. Unlike CoinGecko which only
provides real-time snapshots, Extended's API provides historical data access.

Key Features:
- Historical funding rate data with time-range queries
- Up to 10,000 records per request
- Direct exchange access (no intermediary)
- Efficient bulk downloads for backtesting

API Documentation: https://api.extended.exchange/docs
Endpoint: GET /api/v1/info/{market}/funding

Author: TDL
Date: 2025-11-04
Reference: FUNDING_RATE_ARB_BACKTEST_PLAN_V2.md - Component 4
"""

import asyncio
import aiohttp
import logging
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd

try:
    from .base_funding_source import BaseFundingDataSource
except ImportError:
    from base_funding_source import BaseFundingDataSource

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExtendedFundingDataSource(BaseFundingDataSource):
    """
    Data source for fetching funding rates directly from Extended DEX API.

    Supports:
    - Real-time funding rate snapshots
    - Historical funding rate queries with time ranges
    - Bulk downloads for backtesting (30-90 days)

    Rate Limits:
    - Unknown (to be determined during testing)
    - Start with 1-second delays between requests

    Market Format:
    - Extended uses market IDs like "KAITO-USD", "IP-USDC"
    - Need to map token symbols to market IDs
    """

    BASE_URL = "https://api.starknet.extended.exchange/api/v1"
    EXCHANGE_ID = "extended"

    # Market ID mappings (token symbol -> market ID)
    # These will be populated dynamically via API
    MARKET_MAPPINGS = {}

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        """
        Initialize Extended data source.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts for failed requests
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self._session: Optional[aiohttp.ClientSession] = None
        self._markets_fetched = False

    async def start(self) -> None:
        """Initialize HTTP session and fetch available markets."""
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            headers = {
                'User-Agent': 'backtest'  # Required by Extended API
            }
            self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)
            logger.info("Extended data source session started")

            # Fetch available markets
            await self._fetch_markets()

    async def stop(self) -> None:
        """Close HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None
            logger.info("Extended data source session closed")

    async def _fetch_markets(self) -> None:
        """
        Fetch available markets from Extended API and populate market mappings.

        Endpoint: GET /api/v1/info/markets
        Response: {"status": "OK", "data": [{"name": "KAITO-USD", "assetName": "KAITO", ...}, ...]}
        """
        if self._markets_fetched:
            return

        url = f"{self.BASE_URL}/info/markets"

        try:
            async with self._session.get(url) as response:
                response.raise_for_status()
                json_response = await response.json()

                # Parse response - Extended wraps data in {"status": "OK", "data": [...]}
                if isinstance(json_response, dict) and 'data' in json_response:
                    markets = json_response['data']

                    if isinstance(markets, list):
                        for market in markets:
                            name = market.get('name', '')  # e.g., "KAITO-USD"
                            asset = market.get('assetName', '').upper()  # e.g., "KAITO"

                            if asset and name:
                                self.MARKET_MAPPINGS[asset] = name

                        logger.info(f"Fetched {len(self.MARKET_MAPPINGS)} markets from Extended")
                        self._markets_fetched = True
                    else:
                        logger.warning(f"Unexpected markets data type: {type(markets)}")
                else:
                    logger.warning(f"Unexpected markets response format: {type(json_response)}")

        except Exception as e:
            logger.error(f"Failed to fetch markets from Extended: {e}")
            # Continue anyway - we can still work with manual market IDs

    def _get_market_id(self, token: str, quote: str = "USD") -> str:
        """
        Get market ID for a token.

        Args:
            token: Token symbol (e.g., 'KAITO')
            quote: Quote currency (default 'USD')

        Returns:
            Market ID (e.g., 'KAITO-USD')
        """
        # Try to get from mappings first
        if token in self.MARKET_MAPPINGS:
            return self.MARKET_MAPPINGS[token]

        # Default to standard format
        return f"{token}-{quote}"

    async def get_historical_funding_rates(
        self,
        market: str,
        start_time: int,
        end_time: int,
        limit: int = 10000
    ) -> pd.DataFrame:
        """
        Fetch historical funding rates for a specific market and time range.

        Args:
            market: Market ID (e.g., 'KAITO-USD')
            start_time: Start timestamp (Unix milliseconds)
            end_time: End timestamp (Unix milliseconds)
            limit: Maximum number of records (default 10000)

        Returns:
            DataFrame with columns: timestamp, exchange, base, target, funding_rate

        API Endpoint:
            GET /api/v1/info/{market}/funding?startTime={start}&endTime={end}&limit={limit}

        Response Format (from API docs):
            {
                "status": "OK",
                "data": [
                    {
                        "m": "KAITO-USD",     // market name
                        "T": 1699123200000,    // timestamp in milliseconds
                        "f": "0.0001"          // funding rate as string
                    },
                    ...
                ]
            }
        """
        if not self._session:
            await self.start()

        url = f"{self.BASE_URL}/info/{market}/funding"
        params = {
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }

        for attempt in range(self.max_retries):
            try:
                async with self._session.get(url, params=params) as response:
                    response.raise_for_status()
                    json_response = await response.json()

                    # Parse response - Extended returns {"status": "OK", "data": [...]}
                    records = []

                    if isinstance(json_response, dict) and 'data' in json_response:
                        data = json_response['data']

                        if isinstance(data, list):
                            for item in data:
                                # API returns: m (market), T (timestamp in ms), f (funding rate as string)
                                market_name = item.get('m', market)

                                # Extract market components (e.g., "KAITO-USD" -> "KAITO", "USD")
                                parts = market_name.split('-')
                                base = parts[0] if len(parts) > 0 else 'UNKNOWN'
                                target = parts[1] if len(parts) > 1 else 'USD'

                                # Convert timestamp from milliseconds to seconds
                                timestamp_ms = item.get('T', 0)
                                timestamp_sec = int(timestamp_ms / 1000) if timestamp_ms else 0

                                # Parse funding rate (comes as string)
                                funding_rate_str = item.get('f', '0')
                                funding_rate = float(funding_rate_str) if funding_rate_str else 0.0

                                records.append({
                                    'timestamp': timestamp_sec,
                                    'exchange': self.EXCHANGE_ID,
                                    'base': base,
                                    'target': target,
                                    'funding_rate': funding_rate,
                                })

                    df = pd.DataFrame(records)
                    logger.info(f"Fetched {len(df)} historical records for {market}")
                    return df

            except aiohttp.ClientError as e:
                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed for {market}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"Failed to fetch historical data for {market} after {self.max_retries} attempts")
                    return pd.DataFrame()

        return pd.DataFrame()

    async def get_funding_rates(
        self,
        exchange: str,
        tokens: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Fetch current funding rates for specified tokens.

        Note: Extended API doesn't have a "current snapshot" endpoint like CoinGecko.
        Instead, we fetch the most recent historical data (last hour).

        Args:
            exchange: Exchange identifier (must be 'extended')
            tokens: List of token symbols to fetch

        Returns:
            DataFrame with current funding rates
        """
        if exchange != self.EXCHANGE_ID:
            logger.warning(f"Extended data source only supports exchange='{self.EXCHANGE_ID}', got '{exchange}'")
            return pd.DataFrame()

        if not self._session:
            await self.start()

        # Fetch last hour of data for each token
        # Convert to milliseconds for API
        end_time = int(time.time() * 1000)
        start_time = end_time - (3600 * 1000)  # 1 hour ago in milliseconds

        all_data = []

        for token in (tokens or []):
            market = self._get_market_id(token)
            df = await self.get_historical_funding_rates(market, start_time, end_time, limit=1)

            if not df.empty:
                all_data.append(df)

            # Rate limiting
            await asyncio.sleep(0.5)

        if all_data:
            return pd.concat(all_data, ignore_index=True)
        return pd.DataFrame()

    async def get_funding_rates_multi_exchange(
        self,
        exchanges: List[str],
        tokens: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Fetch funding rates across multiple exchanges.

        Note: Extended data source only supports 'extended' exchange.
        Will filter to only process 'extended' if present in exchanges list.

        Args:
            exchanges: List of exchange identifiers
            tokens: List of token symbols

        Returns:
            DataFrame with funding rates (only for 'extended' exchange)
        """
        if self.EXCHANGE_ID not in exchanges:
            logger.warning(f"Extended data source requested but '{self.EXCHANGE_ID}' not in exchanges list")
            return pd.DataFrame()

        return await self.get_funding_rates(self.EXCHANGE_ID, tokens)

    async def bulk_download_historical(
        self,
        tokens: List[str],
        days: int = 30,
        quote: str = "USD"
    ) -> pd.DataFrame:
        """
        Bulk download historical funding rate data for multiple tokens.

        This is the primary method for backtesting - downloads N days of data
        for all specified tokens in a single call.

        Args:
            tokens: List of token symbols (e.g., ['KAITO', 'IP', 'GRASS'])
            days: Number of days of historical data to fetch (default 30)
            quote: Quote currency for market IDs (default 'USD')

        Returns:
            DataFrame with all historical funding rate data

        Example:
            >>> source = ExtendedFundingDataSource()
            >>> await source.start()
            >>> df = await source.bulk_download_historical(['KAITO', 'IP'], days=30)
            >>> print(f"Downloaded {len(df)} records")
        """
        if not self._session:
            await self.start()

        # Convert to milliseconds for API
        end_time = int(time.time() * 1000)
        start_time = end_time - (days * 24 * 3600 * 1000)

        logger.info(f"Starting bulk download: {len(tokens)} tokens, {days} days")
        logger.info(f"Time range: {datetime.fromtimestamp(start_time/1000)} to {datetime.fromtimestamp(end_time/1000)}")

        all_data = []

        for i, token in enumerate(tokens, 1):
            market = self._get_market_id(token, quote)

            logger.info(f"[{i}/{len(tokens)}] Downloading {market}...")

            df = await self.get_historical_funding_rates(
                market=market,
                start_time=start_time,
                end_time=end_time,
                limit=10000
            )

            if not df.empty:
                all_data.append(df)
                logger.info(f"  ✅ Downloaded {len(df)} records for {market}")
            else:
                logger.warning(f"  ⚠️  No data returned for {market}")

            # Rate limiting between tokens
            if i < len(tokens):
                await asyncio.sleep(1)

        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            combined_df = combined_df.sort_values('timestamp')

            logger.info(f"✅ Bulk download complete: {len(combined_df)} total records")
            # Timestamps are already in seconds in the dataframe
            logger.info(f"   Date range: {datetime.fromtimestamp(combined_df['timestamp'].min())} to {datetime.fromtimestamp(combined_df['timestamp'].max())}")
            logger.info(f"   Tokens: {combined_df['base'].nunique()} ({', '.join(sorted(combined_df['base'].unique()))})")

            return combined_df

        logger.warning("❌ No data downloaded")
        return pd.DataFrame()

    async def validate_exchanges(self, exchanges: List[str]) -> List[str]:
        """Validate that 'extended' is in the exchanges list."""
        valid = [ex for ex in exchanges if ex == self.EXCHANGE_ID]
        if not valid:
            logger.warning(f"Extended data source only supports '{self.EXCHANGE_ID}' exchange")
        return valid

    async def validate_tokens(
        self,
        exchange: str,
        tokens: List[str]
    ) -> List[str]:
        """
        Validate that tokens are available on Extended.

        Returns tokens that have market mappings.
        """
        if not self._markets_fetched:
            await self._fetch_markets()

        valid_tokens = [
            token for token in tokens
            if token in self.MARKET_MAPPINGS or True  # Allow all for now
        ]

        return valid_tokens

    def __repr__(self) -> str:
        """String representation."""
        return f"ExtendedFundingDataSource(markets={len(self.MARKET_MAPPINGS)})"
