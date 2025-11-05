"""
Mock Perpetual Connectors for Backtesting

These connectors simulate Extended and Lighter perpetual exchanges
using pre-loaded historical funding rate data.

Author: TDL
Date: 2025-11-04
"""

from decimal import Decimal
from typing import Optional
from hummingbot.core.data_type.funding_info import FundingInfo
from hummingbot.core.data_type.common import PositionMode, OrderType, TradeType, PositionAction
from hummingbot.core.data_type.trade_fee import TradeFeeSchema


class MockPerpetualConnectorBase:
    """
    Base class for mock perpetual connectors used in backtesting.

    Provides minimal interface needed by v2_funding_rate_arb strategy.
    """

    def __init__(self, connector_name: str, data_provider):
        """
        Initialize mock connector.

        Args:
            connector_name: Name of the connector (e.g., "extended_perpetual")
            data_provider: BacktestingDataProvider instance with funding data
        """
        self.connector_name = connector_name
        self.data_provider = data_provider
        self._position_mode = PositionMode.ONEWAY
        self._leverage = {}
        self.trading_rules = {}  # Trading rules (populated by backtesting engine)

    def set_position_mode(self, position_mode: PositionMode):
        """Set position mode (ONEWAY or HEDGE)."""
        self._position_mode = position_mode

    def set_leverage(self, trading_pair: str, leverage: int):
        """Set leverage for a trading pair."""
        self._leverage[trading_pair] = leverage

    async def _update_trading_rules(self):
        """Update trading rules (mock implementation for backtesting)."""
        # Mock implementation - no actual API calls needed in backtesting
        pass

    def get_funding_info(self, trading_pair: str) -> Optional[FundingInfo]:
        """
        Get historical funding info at current backtest timestamp.

        Delegates to BacktestingDataProvider which has time awareness.

        Args:
            trading_pair: Trading pair (e.g., "KAITO-USD")

        Returns:
            FundingInfo object with historical data at current backtest time
        """
        return self.data_provider.get_funding_info(
            self.connector_name,
            trading_pair
        )

    def get_fee(
        self,
        base_currency: str,
        quote_currency: str,
        order_type: OrderType,
        order_side: TradeType,
        amount: Decimal,
        price: Decimal,
        is_maker: bool = False,
        position_action: PositionAction = PositionAction.OPEN
    ) -> TradeFeeSchema:
        """
        Return trading fee for the exchange.

        Actual fee structure (verified 2025-11-05):
        - Extended: 0% maker, 0.025% taker (market orders)
        - Lighter: 0% maker, 0% taker (NO FEES)
        """
        if self.connector_name == "extended_perpetual":
            maker_fee = Decimal("0.0")
            taker_fee = Decimal("0.00025")  # 0.025%
        elif self.connector_name == "lighter_perpetual":
            maker_fee = Decimal("0.0")
            taker_fee = Decimal("0.0")  # NO FEES
        else:
            # Default fees
            maker_fee = Decimal("0.0005")
            taker_fee = Decimal("0.0005")

        fee_pct = maker_fee if is_maker else taker_fee

        return TradeFeeSchema(
            maker_percent_fee_decimal=maker_fee,
            taker_percent_fee_decimal=taker_fee,
            percent_fee_token=quote_currency,
            buy_percent_fee_deduction_from_returns=True
        )


class ExtendedPerpetualMockConnector(MockPerpetualConnectorBase):
    """
    Mock Extended Perpetual connector for backtesting.

    Provides historical funding rate data from Extended DEX.
    """

    def __init__(self, data_provider):
        super().__init__("extended_perpetual", data_provider)


class LighterPerpetualMockConnector(MockPerpetualConnectorBase):
    """
    Mock Lighter Perpetual connector for backtesting.

    Provides historical funding rate data from Lighter DEX.
    """

    def __init__(self, data_provider):
        super().__init__("lighter_perpetual", data_provider)
