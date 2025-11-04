"""
Base Interface for Funding Rate Data Sources

This abstract base class defines the interface that all funding rate data sources
must implement, enabling a modular architecture where data sources can be swapped
without changing downstream code (FundingRateCollector, BacktestDataProvider).

All concrete implementations must provide:
- Session lifecycle management (start/stop)
- Single exchange funding rate fetching
- Multi-exchange funding rate fetching
- Standardized DataFrame output schema
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import pandas as pd


class BaseFundingDataSource(ABC):
    """Abstract base class for funding rate data sources."""

    # Standard DataFrame schema that all sources must return
    REQUIRED_COLUMNS = [
        'timestamp',      # Unix timestamp (int)
        'exchange',       # Exchange identifier (str)
        'base',          # Base token symbol (str, e.g., 'KAITO')
        'target',        # Quote currency (str, e.g., 'USD')
        'funding_rate',  # Hourly funding rate (float, e.g., 0.001 = 0.1%)
        'index',         # Index price (float)
    ]

    @abstractmethod
    async def start(self) -> None:
        """
        Initialize the data source and any required resources.

        This method should:
        - Create HTTP sessions
        - Validate API keys/credentials
        - Initialize connection pools
        - Perform any necessary authentication
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """
        Clean up resources when done.

        This method should:
        - Close HTTP sessions
        - Release connection pools
        - Clean up temporary resources
        """
        pass

    @abstractmethod
    async def get_funding_rates(
        self,
        exchange: str,
        tokens: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Fetch current funding rates for a single exchange.

        Args:
            exchange: Exchange identifier (e.g., 'lighter', 'extended')
            tokens: Optional list of token symbols to filter by (e.g., ['KAITO', 'IP'])
                   If None, fetch all available tokens

        Returns:
            DataFrame with columns: timestamp, exchange, base, target, funding_rate, index
            Must contain only rows for the specified exchange
            If tokens specified, only return rows for those tokens

        Schema:
            - timestamp (int): Unix timestamp when data was collected
            - exchange (str): Exchange identifier
            - base (str): Token symbol (e.g., 'KAITO')
            - target (str): Quote currency (e.g., 'USD')
            - funding_rate (float): Hourly funding rate (e.g., 0.001 = 0.1%)
            - index (float): Index/mark price
        """
        pass

    @abstractmethod
    async def get_funding_rates_multi_exchange(
        self,
        exchanges: List[str],
        tokens: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Fetch current funding rates across multiple exchanges.

        Args:
            exchanges: List of exchange identifiers (e.g., ['lighter', 'extended'])
            tokens: Optional list of token symbols to filter by

        Returns:
            DataFrame with same schema as get_funding_rates(), but containing
            data from all specified exchanges

        Implementation Note:
            This method should handle rate limiting appropriately for the
            specific data source (concurrent vs sequential requests)
        """
        pass

    async def validate_exchanges(self, exchanges: List[str]) -> List[str]:
        """
        Validate that exchanges are supported by this data source.

        Args:
            exchanges: List of exchange identifiers to validate

        Returns:
            List of valid exchange identifiers

        Note:
            Default implementation returns all exchanges as valid.
            Override if the data source has specific exchange requirements.
        """
        return exchanges

    async def validate_tokens(
        self,
        exchange: str,
        tokens: List[str]
    ) -> List[str]:
        """
        Validate that tokens are available on the specified exchange.

        Args:
            exchange: Exchange identifier
            tokens: List of token symbols to validate

        Returns:
            List of valid token symbols available on the exchange

        Note:
            Default implementation returns all tokens as valid.
            Override if the data source can provide token availability checking.
        """
        return tokens

    def validate_dataframe(self, df: pd.DataFrame) -> bool:
        """
        Validate that a DataFrame conforms to the required schema.

        Args:
            df: DataFrame to validate

        Returns:
            True if valid, False otherwise

        Checks:
            - All required columns present
            - No null values in critical fields
            - Correct data types
        """
        if df.empty:
            return True

        # Check required columns
        missing_cols = set(self.REQUIRED_COLUMNS) - set(df.columns)
        if missing_cols:
            raise ValueError(f"DataFrame missing required columns: {missing_cols}")

        # Check for nulls in critical fields
        critical_fields = ['timestamp', 'exchange', 'base', 'funding_rate']
        nulls = df[critical_fields].isnull().any()
        if nulls.any():
            null_cols = nulls[nulls].index.tolist()
            raise ValueError(f"DataFrame has null values in critical fields: {null_cols}")

        # Check data types
        if not pd.api.types.is_numeric_dtype(df['timestamp']):
            raise ValueError("timestamp must be numeric (Unix timestamp)")
        if not pd.api.types.is_numeric_dtype(df['funding_rate']):
            raise ValueError("funding_rate must be numeric")
        if not pd.api.types.is_numeric_dtype(df['index']):
            raise ValueError("index must be numeric")

        return True

    def __repr__(self) -> str:
        """String representation of the data source."""
        return f"{self.__class__.__name__}()"
