"""
CoinGecko Funding Rate Data Source

This module provides an interface to CoinGecko's derivatives API for fetching
funding rate data from perpetual DEX markets (Extended, Lighter, Variational).

Used for backtesting the funding rate arbitrage strategy.

Author: TDL
Date: 2024-11-03
Reference: FUNDING_RATE_ARB_BACKTEST_PLAN.md - Component 1
"""

import asyncio
import aiohttp
import logging
import time
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
import pandas as pd
from decimal import Decimal

try:
    from .base_funding_source import BaseFundingDataSource
except ImportError:
    from base_funding_source import BaseFundingDataSource

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CoinGeckoFundingDataSource(BaseFundingDataSource):
    """
    Data source for fetching funding rates from CoinGecko derivatives API.

    Supports:
    - Multiple perpetual DEX exchanges (Extended, Lighter, Variational)
    - Token filtering
    - Async concurrent requests
    - Error handling and retries
    - Rate limiting

    Usage:
        >>> cg = CoinGeckoFundingDataSource(api_key="your_key")
        >>> await cg.start()
        >>> funding_data = await cg.get_funding_rates("extended", ["KAITO", "MON"])
        >>> await cg.stop()
    """

    # API endpoints
    BASE_URL = "https://api.coingecko.com/api/v3"
    PRO_BASE_URL = "https://pro-api.coingecko.com/api/v3"
    DEMO_BASE_URL = "https://api.coingecko.com/api/v3"  # Demo keys use same URL as free

    # Default settings
    DEFAULT_TIMEOUT = 30  # seconds
    DEFAULT_RETRY_ATTEMPTS = 3
    DEFAULT_RETRY_DELAY = 5  # seconds

    def __init__(
        self,
        api_key: Optional[str] = None,
        user_agent: str = "backtest",
        timeout: int = DEFAULT_TIMEOUT,
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS
    ):
        """
        Initialize CoinGecko funding rate data source.

        Args:
            api_key: CoinGecko API key (None for free tier)
            user_agent: User agent string for API requests
            timeout: Request timeout in seconds
            retry_attempts: Number of retry attempts on failure
        """
        self.api_key = api_key
        self.user_agent = user_agent

        # Determine API type: For now, assume all CG- keys are Demo keys
        # Demo keys: use api.coingecko.com with query parameter
        # Pro keys: use pro-api.coingecko.com with header
        self.is_demo = api_key and api_key.startswith("CG-")
        self.use_pro = bool(api_key) and not self.is_demo

        self.base_url = self.PRO_BASE_URL if self.use_pro else self.BASE_URL
        self.timeout = timeout
        self.retry_attempts = retry_attempts

        # Session management
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_created_at: Optional[float] = None

        # Cache for exchange list
        self._exchange_list_cache: Optional[List[Dict]] = None
        self._exchange_list_cache_time: Optional[float] = None
        self._exchange_list_cache_ttl: int = 3600  # 1 hour

        logger.info(f"CoinGecko Funding Data Source initialized (Pro: {self.use_pro})")

    async def start(self):
        """
        Start the data source by creating HTTP session.
        Call this before making any requests.
        """
        if self._session is None or self._session.closed:
            headers = {
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            }

            # For Pro API, add the API key header
            if self.api_key:
                headers["x-cg-pro-api-key"] = self.api_key

            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=timeout
            )
            self._session_created_at = time.time()
            logger.info(f"CoinGecko session started (User-Agent: {self.user_agent})")

    async def stop(self):
        """
        Stop the data source by closing HTTP session.
        Call this when done to clean up resources.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self._session_created_at = None
            logger.info("CoinGecko session stopped")

    async def __aenter__(self):
        """Context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.stop()

    def _ensure_session(self):
        """Ensure session is created before making requests."""
        if self._session is None or self._session.closed:
            raise RuntimeError(
                "Session not started. Call 'await start()' or use as context manager."
            )

    def _add_api_key_params(self, params: Optional[Dict] = None) -> Dict:
        """
        Add API key to request parameters if using Demo API.

        For Demo keys, the key must be passed as query parameter x_cg_demo_api_key.
        For Pro keys, it's passed as header (done in session creation).

        Args:
            params: Existing parameters dict

        Returns:
            Parameters dict with API key added if needed
        """
        if params is None:
            params = {}

        if self.is_demo and self.api_key:
            params["x_cg_demo_api_key"] = self.api_key

        return params


    async def get_exchange_list(self, force_refresh: bool = False) -> List[Dict]:
        """
        Get list of all derivative exchanges from CoinGecko.

        Args:
            force_refresh: Force refresh cache even if not expired

        Returns:
            List of exchange dictionaries with id, name, and other metadata

        Example:
            >>> exchanges = await cg.get_exchange_list()
            >>> print([ex['id'] for ex in exchanges])
            ['binance_futures', 'bybit', 'extended', 'lighter', ...]
        """
        self._ensure_session()

        # Check cache
        current_time = time.time()
        if (not force_refresh and
            self._exchange_list_cache is not None and
            self._exchange_list_cache_time is not None and
            (current_time - self._exchange_list_cache_time) < self._exchange_list_cache_ttl):
            logger.debug("Returning cached exchange list")
            return self._exchange_list_cache

        # Fetch from API
        url = f"{self.base_url}/derivatives/exchanges"
        params = self._add_api_key_params()  # Add Demo API key if needed
        logger.info(f"Fetching exchange list from: {url}")

        try:
            async with self._session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()

                # Cache the result
                self._exchange_list_cache = data
                self._exchange_list_cache_time = current_time

                logger.info(f"Fetched {len(data)} derivative exchanges")
                return data

        except aiohttp.ClientError as e:
            logger.error(f"Failed to fetch exchange list: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching exchange list: {e}")
            raise

    async def validate_exchange_availability(
        self,
        exchange_id: str,
        verbose: bool = True
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Validate if an exchange exists and has derivatives data on CoinGecko.

        Args:
            exchange_id: Exchange identifier (e.g., "extended", "lighter")
            verbose: Log detailed information

        Returns:
            Tuple of (is_available: bool, exchange_info: Dict or None)

        Example:
            >>> available, info = await cg.validate_exchange_availability("extended")
            >>> if available:
            ...     print(f"Exchange: {info['name']}")
        """
        self._ensure_session()

        try:
            exchanges = await self.get_exchange_list()

            # Search for exchange by ID
            exchange_info = None
            for exchange in exchanges:
                if exchange.get('id', '').lower() == exchange_id.lower():
                    exchange_info = exchange
                    break

            if exchange_info:
                if verbose:
                    logger.info(
                        f"✅ Exchange '{exchange_id}' found: {exchange_info.get('name', 'N/A')}"
                    )
                return True, exchange_info
            else:
                if verbose:
                    logger.warning(
                        f"❌ Exchange '{exchange_id}' not found on CoinGecko"
                    )
                return False, None

        except Exception as e:
            logger.error(f"Error validating exchange '{exchange_id}': {e}")
            return False, None

    async def validate_multiple_exchanges(
        self,
        exchange_ids: List[str]
    ) -> Dict[str, Tuple[bool, Optional[Dict]]]:
        """
        Validate multiple exchanges concurrently.

        Args:
            exchange_ids: List of exchange IDs to validate

        Returns:
            Dictionary mapping exchange_id to (is_available, exchange_info)

        Example:
            >>> results = await cg.validate_multiple_exchanges(
            ...     ["extended", "lighter", "variational"]
            ... )
            >>> for ex_id, (available, info) in results.items():
            ...     print(f"{ex_id}: {available}")
        """
        self._ensure_session()

        # Fetch exchange list once
        exchanges = await self.get_exchange_list()

        results = {}
        for exchange_id in exchange_ids:
            # Search for exchange
            exchange_info = None
            for exchange in exchanges:
                if exchange.get('id', '').lower() == exchange_id.lower():
                    exchange_info = exchange
                    break

            if exchange_info:
                results[exchange_id] = (True, exchange_info)
                logger.info(f"✅ {exchange_id}: {exchange_info.get('name', 'N/A')}")
            else:
                results[exchange_id] = (False, None)
                logger.warning(f"❌ {exchange_id}: Not found")

        return results


    async def get_funding_rates(
        self,
        exchange_id: str,
        tokens: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Get current funding rates for a specific exchange.

        Uses CoinGecko API: GET /derivatives/exchanges/{id}?include_tickers=unexpired

        Args:
            exchange_id: Exchange identifier (e.g., "binance_futures", "bybit")
            tokens: Optional list of tokens to filter (e.g., ["BTC", "ETH"])
                   If None, returns all available tokens

        Returns:
            DataFrame with columns:
            - timestamp: Unix timestamp of data collection
            - exchange: Exchange ID
            - symbol: Full contract symbol (e.g., "BTCUSDT")
            - base: Base token (e.g., "BTC")
            - target: Quote currency (e.g., "USDT")
            - coin_id: CoinGecko coin identifier
            - funding_rate: Current funding rate (as decimal, e.g., 0.01 = 1%)
            - index: Index/reference price
            - last: Last traded price
            - index_basis_percentage: Basis as percentage
            - open_interest_usd: Open interest in USD
            - h24_volume: 24-hour volume
            - h24_percentage_change: 24-hour price change percentage
            - contract_type: Type of contract (perpetual/futures)
            - last_traded: Last update timestamp

        Example:
            >>> df = await cg.get_funding_rates("binance_futures", ["BTC", "ETH"])
            >>> print(df[['base', 'funding_rate', 'index']])
        """
        self._ensure_session()

        # Build URL with include_tickers parameter
        url = f"{self.base_url}/derivatives/exchanges/{exchange_id}"
        params = {"include_tickers": "unexpired"}  # Only get active contracts
        params = self._add_api_key_params(params)  # Add Demo API key if needed

        logger.info(f"Fetching funding rates from {exchange_id}...")

        try:
            async with self._session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()

            # Extract tickers
            tickers = data.get('tickers', [])

            if not tickers:
                logger.warning(f"No tickers found for {exchange_id}")
                return pd.DataFrame()

            # Parse tickers into structured data
            funding_data = []
            current_timestamp = int(time.time())

            for ticker in tickers:
                # Only include perpetual contracts first
                contract_type = ticker.get('contract_type', '').lower()
                if 'perpetual' not in contract_type:
                    continue

                # Get underlying asset from 'base' field
                # This is the token symbol (e.g., "BTC", "ETH", "1000BONK")
                base = ticker.get('base', '').upper()

                # Skip if no base token
                if not base:
                    continue

                # Filter by tokens if specified
                if tokens and base not in tokens:
                    continue

                # Parse funding rate (can be None)
                funding_rate = ticker.get('funding_rate')
                if funding_rate is None:
                    funding_rate = 0.0
                else:
                    funding_rate = float(funding_rate)

                funding_data.append({
                    'timestamp': current_timestamp,
                    'exchange': exchange_id,
                    'symbol': ticker.get('symbol', ''),
                    'base': base,  # Base token (BTC, ETH, etc.)
                    'target': ticker.get('target', '').upper(),  # Quote currency (USDT, USDC)
                    'coin_id': ticker.get('coin_id', ''),  # CoinGecko coin ID
                    'funding_rate': funding_rate,
                    'index': float(ticker.get('index', 0)),  # Index/reference price
                    'last': float(ticker.get('last', 0)),  # Last traded price
                    'index_basis_percentage': float(ticker.get('index_basis_percentage', 0)),
                    'open_interest_usd': float(ticker.get('open_interest_usd', 0)),
                    'h24_volume': float(ticker.get('h24_volume', 0)),
                    'h24_percentage_change': float(ticker.get('h24_percentage_change', 0)),
                    'contract_type': ticker.get('contract_type', ''),
                    'last_traded': ticker.get('last_traded', 0),
                })

            df = pd.DataFrame(funding_data)

            if not df.empty:
                logger.info(
                    f"✅ Fetched {len(df)} funding rates from {exchange_id}"
                )
            else:
                logger.warning(f"No matching tokens found on {exchange_id}")

            return df

        except aiohttp.ClientResponseError as e:
            if e.status == 404:
                logger.error(f"Exchange '{exchange_id}' not found (404)")
            else:
                logger.error(f"HTTP error fetching from {exchange_id}: {e.status} - {e.message}")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching from {exchange_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching from {exchange_id}: {e}")
            raise


    async def get_funding_rates_multi_exchange(
        self,
        exchanges: List[str],
        tokens: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Get funding rates from multiple exchanges concurrently.

        Args:
            exchanges: List of exchange IDs (e.g., ["extended", "lighter", "variational"])
            tokens: Optional list of tokens to filter

        Returns:
            Combined DataFrame from all exchanges

        Example:
            >>> df = await cg.get_funding_rates_multi_exchange(
            ...     ["extended", "lighter", "variational"],
            ...     ["KAITO", "MON", "IP"]
            ... )
            >>> print(df.groupby('exchange')['token'].count())
        """
        self._ensure_session()

        logger.info(f"Fetching funding rates from {len(exchanges)} exchanges...")

        # Fetch sequentially with delay to avoid rate limiting
        # (Demo API has strict rate limits)
        results = []
        for i, exchange_id in enumerate(exchanges):
            try:
                result = await self.get_funding_rates(exchange_id, tokens)
                results.append(result)

                # Add delay between requests (except for last one)
                if i < len(exchanges) - 1:
                    await asyncio.sleep(2)  # 2 second delay between requests

            except Exception as e:
                results.append(e)

        # Combine results
        dfs = []
        for exchange_id, result in zip(exchanges, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to fetch from {exchange_id}: {result}")
                continue

            if isinstance(result, pd.DataFrame) and not result.empty:
                dfs.append(result)

        if not dfs:
            logger.warning("No funding rate data collected from any exchange")
            return pd.DataFrame()

        # Concatenate all dataframes
        combined_df = pd.concat(dfs, ignore_index=True)

        logger.info(
            f"✅ Collected {len(combined_df)} funding rates from "
            f"{len(dfs)}/{len(exchanges)} exchanges"
        )

        return combined_df


    def calculate_spreads(self, funding_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate funding rate spreads between exchanges for each token.

        Args:
            funding_df: DataFrame with funding rates from multiple exchanges

        Returns:
            DataFrame with spread calculations

        Example:
            >>> df = await cg.get_funding_rates_multi_exchange(...)
            >>> spreads = cg.calculate_spreads(df)
            >>> print(spreads[['base', 'binance_futures_bybit_spread']])
        """
        if funding_df.empty:
            return pd.DataFrame()

        # Pivot to get rates by exchange (using 'base' as the token identifier)
        pivot_df = funding_df.pivot_table(
            index='base',
            columns='exchange',
            values='funding_rate',
            aggfunc='first'
        )

        spreads = pivot_df.copy()
        exchanges = pivot_df.columns.tolist()

        # Calculate all pairwise spreads
        for i, ex1 in enumerate(exchanges):
            for ex2 in exchanges[i+1:]:
                spread_col = f"{ex1}_{ex2}_spread"
                spreads[spread_col] = abs(pivot_df[ex1] - pivot_df[ex2])

        spreads.reset_index(inplace=True)

        return spreads
