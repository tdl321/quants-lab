"""
Lighter DEX Funding Rate Data Source

This module provides an interface to Lighter's native API for fetching
funding rate data directly from the exchange.

Key Features:
- Historical funding rate data with time-range queries
- Hourly funding rates
- Direct exchange access (no intermediary)
- Efficient bulk downloads for backtesting

API Base URL: https://mainnet.zklighter.elliot.ai
Documentation: https://github.com/elliottech/lighter-python

Author: TDL
Date: 2025-11-04
"""

import asyncio
import aiohttp
import logging
import time
from typing import List, Dict, Optional
from datetime import datetime
import pandas as pd

try:
    from .base_funding_source import BaseFundingDataSource
except ImportError:
    from base_funding_source import BaseFundingDataSource

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LighterFundingDataSource(BaseFundingDataSource):
    """
    Data source for fetching funding rates directly from Lighter DEX API.

    Supports:
    - Real-time funding rate snapshots
    - Historical funding rate queries with time ranges
    - Bulk downloads for backtesting (30-90 days)

    Market Format:
    - Lighter uses market IDs (integers) like 33 for KAITO
    - Need to map token symbols to market IDs via /orderBooks endpoint
    """

    BASE_URL = "https://mainnet.zklighter.elliot.ai"
    EXCHANGE_ID = "lighter"

    # Market ID mappings (token symbol -> market ID as integer)
    # These will be populated dynamically via API
    MARKET_MAPPINGS = {}  # e.g., {'KAITO': 33, 'IP': 34}

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        """
        Initialize Lighter data source.

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
            self._session = aiohttp.ClientSession(timeout=timeout)
            logger.info("Lighter data source session started")

            # Fetch available markets
            await self._fetch_markets()

    async def stop(self) -> None:
        """Close HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None
            logger.info("Lighter data source session closed")

    async def _fetch_markets(self) -> None:
        """
        Fetch available markets from Lighter API and populate market mappings.

        Endpoint: GET /api/v1/orderBooks
        Response: {"code": 200, "order_books": [{"symbol": "KAITO", "market_id": 33, ...}, ...]}
        """
        if self._markets_fetched:
            return

        url = f"{self.BASE_URL}/api/v1/orderBooks"

        try:
            async with self._session.get(url) as response:
                response.raise_for_status()
                json_response = await response.json()

                # Parse response - Lighter returns {"code": 200, "order_books": [...]}
                if isinstance(json_response, dict) and 'order_books' in json_response:
                    order_books = json_response['order_books']

                    if isinstance(order_books, list):
                        for book in order_books:
                            symbol = book.get('symbol', '').upper()
                            market_id = book.get('market_id')
                            status = book.get('status', '')

                            if symbol and market_id is not None:
                                self.MARKET_MAPPINGS[symbol] = market_id
                                logger.debug(f"Market: {symbol} -> {market_id} ({status})")

                        logger.info(f"Fetched {len(self.MARKET_MAPPINGS)} markets from Lighter")
                        self._markets_fetched = True
                    else:
                        logger.warning(f"Unexpected order_books data type: {type(order_books)}")
                else:
                    logger.warning(f"Unexpected response format: {type(json_response)}")

        except Exception as e:
            logger.error(f"Failed to fetch markets from Lighter: {e}")
            # Continue anyway - we can still work with manual market IDs

    def _get_market_id(self, token: str) -> Optional[int]:
        """
        Get market ID for a token.

        Args:
            token: Token symbol (e.g., 'KAITO')

        Returns:
            Market ID (integer) or None if not found
        """
        return self.MARKET_MAPPINGS.get(token.upper())

    async def get_historical_funding_rates(
        self,
        market_id: int,
        start_time: int,
        end_time: int,
        resolution: str = "1h"
    ) -> pd.DataFrame:
        """
        Fetch historical funding rates for a specific market and time range.

        Args:
            market_id: Market ID (integer, e.g., 33 for KAITO)
            start_time: Start timestamp (Unix seconds)
            end_time: End timestamp (Unix seconds)
            resolution: Time resolution (default "1h" for hourly)

        Returns:
            DataFrame with columns: timestamp, exchange, base, target, funding_rate

        API Endpoint:
            GET /api/v1/fundings?market_id={id}&resolution={res}&start_timestamp={start}&end_timestamp={end}&count_back={count}

        Response Format (from API):
            {
                "code": 200,
                "resolution": "1h",
                "fundings": [
                    {
                        "timestamp": 1761685200,     // Unix seconds
                        "value": "0.00006",          // Funding rate value (string)
                        "rate": "0.0058",            // Rate percentage (string)
                        "direction": "short"         // "short" or "long"
                    },
                    ...
                ]
            }
        """
        if not self._session:
            await self.start()

        # Calculate count_back based on time range and resolution
        time_diff = end_time - start_time
        if resolution == "1h":
            count_back = int(time_diff / 3600)  # hours
        elif resolution == "1d":
            count_back = int(time_diff / 86400)  # days
        else:
            count_back = 1000  # default

        url = f"{self.BASE_URL}/api/v1/fundings"
        params = {
            "market_id": market_id,
            "resolution": resolution,
            "start_timestamp": start_time,
            "end_timestamp": end_time,
            "count_back": count_back
        }

        for attempt in range(self.max_retries):
            try:
                async with self._session.get(url, params=params) as response:
                    response.raise_for_status()
                    json_response = await response.json()

                    # Parse response - Lighter returns {"code": 200, "fundings": [...]}
                    records = []

                    if isinstance(json_response, dict) and 'fundings' in json_response:
                        fundings = json_response['fundings']

                        if isinstance(fundings, list):
                            for item in fundings:
                                # API returns: timestamp, value, rate, direction
                                timestamp = item.get('timestamp', 0)
                                value_str = item.get('value', '0')
                                rate_str = item.get('rate', '0')
                                direction = item.get('direction', '')

                                # Convert funding rate from string to float
                                # Use 'value' field as the funding rate
                                funding_rate = float(value_str) if value_str else 0.0

                                # Apply direction: short = positive (you pay), long = negative (you receive)
                                # Actually, need to verify this - for now keep as-is
                                if direction == "long":
                                    funding_rate = -funding_rate

                                # We don't know the token symbol from the response,
                                # so we'll need to get it from the market_id mapping
                                # For now, use placeholder
                                base = "UNKNOWN"
                                for symbol, mid in self.MARKET_MAPPINGS.items():
                                    if mid == market_id:
                                        base = symbol
                                        break

                                records.append({
                                    'timestamp': int(timestamp),
                                    'exchange': self.EXCHANGE_ID,
                                    'base': base,
                                    'target': 'USD',  # Lighter uses USD for all markets
                                    'funding_rate': funding_rate,
                                })

                    df = pd.DataFrame(records)
                    logger.info(f"Fetched {len(df)} historical records for market_id {market_id}")
                    return df

            except aiohttp.ClientError as e:
                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed for market_id {market_id}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"Failed to fetch historical data for market_id {market_id} after {self.max_retries} attempts")
                    return pd.DataFrame()

        return pd.DataFrame()

    async def get_funding_rates(
        self,
        exchange: str,
        tokens: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Fetch current funding rates for specified tokens.

        Fetches the most recent hour of data for each token.

        Args:
            exchange: Exchange identifier (must be 'lighter')
            tokens: List of token symbols to fetch

        Returns:
            DataFrame with current funding rates
        """
        if exchange != self.EXCHANGE_ID:
            logger.warning(f"Lighter data source only supports exchange='{self.EXCHANGE_ID}', got '{exchange}'")
            return pd.DataFrame()

        if not self._session:
            await self.start()

        # Fetch last hour of data for each token (timestamps in seconds)
        end_time = int(time.time())
        start_time = end_time - 3600  # 1 hour ago

        all_data = []

        for token in (tokens or []):
            market_id = self._get_market_id(token)
            if market_id is None:
                logger.warning(f"Market ID not found for token: {token}")
                continue

            df = await self.get_historical_funding_rates(market_id, start_time, end_time, resolution="1h")

            if not df.empty:
                # Get only the most recent record
                df = df.sort_values('timestamp', ascending=False).head(1)
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

        Note: Lighter data source only supports 'lighter' exchange.
        Will filter to only process 'lighter' if present in exchanges list.

        Args:
            exchanges: List of exchange identifiers
            tokens: List of token symbols

        Returns:
            DataFrame with funding rates (only for 'lighter' exchange)
        """
        if self.EXCHANGE_ID not in exchanges:
            logger.warning(f"Lighter data source requested but '{self.EXCHANGE_ID}' not in exchanges list")
            return pd.DataFrame()

        return await self.get_funding_rates(self.EXCHANGE_ID, tokens)

    async def bulk_download_historical(
        self,
        tokens: List[str],
        days: int = 30,
        resolution: str = "1h"
    ) -> pd.DataFrame:
        """
        Bulk download historical funding rate data for multiple tokens.

        This is the primary method for backtesting - downloads N days of data
        for all specified tokens in a single call.

        Args:
            tokens: List of token symbols (e.g., ['KAITO', 'IP', 'GRASS'])
            days: Number of days of historical data to fetch (default 30)
            resolution: Time resolution (default "1h" for hourly)

        Returns:
            DataFrame with all historical funding rate data

        Example:
            >>> source = LighterFundingDataSource()
            >>> await source.start()
            >>> df = await source.bulk_download_historical(['KAITO', 'IP'], days=30)
            >>> print(f"Downloaded {len(df)} records")
        """
        if not self._session:
            await self.start()

        # Timestamps in seconds (not milliseconds like Extended)
        end_time = int(time.time())
        start_time = end_time - (days * 24 * 3600)

        logger.info(f"Starting bulk download: {len(tokens)} tokens, {days} days")
        logger.info(f"Time range: {datetime.fromtimestamp(start_time)} to {datetime.fromtimestamp(end_time)}")

        all_data = []

        for i, token in enumerate(tokens, 1):
            market_id = self._get_market_id(token)
            if market_id is None:
                logger.warning(f"  ⚠️  Market ID not found for {token}")
                continue

            logger.info(f"[{i}/{len(tokens)}] Downloading {token} (market_id: {market_id})...")

            df = await self.get_historical_funding_rates(
                market_id=market_id,
                start_time=start_time,
                end_time=end_time,
                resolution=resolution
            )

            if not df.empty:
                all_data.append(df)
                logger.info(f"  ✅ Downloaded {len(df)} records for {token}")
            else:
                logger.warning(f"  ⚠️  No data returned for {token}")

            # Rate limiting between tokens
            if i < len(tokens):
                await asyncio.sleep(1)

        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            combined_df = combined_df.sort_values('timestamp')

            logger.info(f"✅ Bulk download complete: {len(combined_df)} total records")
            logger.info(f"   Date range: {datetime.fromtimestamp(combined_df['timestamp'].min())} to {datetime.fromtimestamp(combined_df['timestamp'].max())}")
            logger.info(f"   Tokens: {combined_df['base'].nunique()} ({', '.join(sorted(combined_df['base'].unique()))})")

            return combined_df

        logger.warning("❌ No data downloaded")
        return pd.DataFrame()

    async def validate_exchanges(self, exchanges: List[str]) -> List[str]:
        """Validate that 'lighter' is in the exchanges list."""
        valid = [ex for ex in exchanges if ex == self.EXCHANGE_ID]
        if not valid:
            logger.warning(f"Lighter data source only supports '{self.EXCHANGE_ID}' exchange")
        return valid

    async def validate_tokens(
        self,
        exchange: str,
        tokens: List[str]
    ) -> List[str]:
        """
        Validate that tokens are available on Lighter.

        Returns tokens that have market mappings.
        """
        if not self._markets_fetched:
            await self._fetch_markets()

        valid_tokens = [
            token for token in tokens
            if token.upper() in self.MARKET_MAPPINGS
        ]

        invalid = [t for t in tokens if t.upper() not in self.MARKET_MAPPINGS]
        if invalid:
            logger.warning(f"Tokens not found on Lighter: {invalid}")

        return valid_tokens

    def __repr__(self) -> str:
        """String representation."""
        return f"LighterFundingDataSource(markets={len(self.MARKET_MAPPINGS)})"
