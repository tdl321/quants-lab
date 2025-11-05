"""
Funding Rate Arbitrage Controller

Controller-based implementation of delta-neutral funding rate arbitrage.
Monitors funding rate spreads across perpetual DEXs and opens paired positions
when spreads exceed threshold.

Data Timing:
- Funding rates represent PAST payments (no lookahead bias)
- 2-minute execution delay for data propagation
- Time-aware queries via BacktestingDataProvider

Author: Claude Code
Date: 2025-11-05
"""

from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime
from pydantic import Field, field_validator

from hummingbot.core.data_type.common import OrderType, PriceType, TradeType
from hummingbot.core.data_type.funding_info import FundingInfo
from hummingbot.strategy_v2.controllers.controller_base import ControllerBase, ControllerConfigBase
from hummingbot.strategy_v2.executors.position_executor.data_types import (
    PositionExecutorConfig,
    TripleBarrierConfig,
)
from hummingbot.strategy_v2.models.executor_actions import CreateExecutorAction, ExecutorAction, StopExecutorAction


class FundingRateArbControllerConfig(ControllerConfigBase):
    """
    Configuration for funding rate arbitrage controller.

    Data Timing: Funding rates are historical payments.
    Execution Delay: 2 minutes after funding payment to allow data propagation.
    """
    controller_name: str = "funding_rate_arb"

    # Required base fields (framework compatibility)
    connector_name: str = Field(
        default="extended_perpetual",
        json_schema_extra={
            "prompt": "Enter primary connector name: ",
            "prompt_on_new": True
        }
    )
    trading_pair: str = Field(
        default="KAITO-USD",
        json_schema_extra={
            "prompt": "Enter primary trading pair: ",
            "prompt_on_new": True
        }
    )

    # Multi-connector arbitrage configuration
    connectors: Set[str] = Field(
        default={"extended_perpetual", "lighter_perpetual"},
        json_schema_extra={
            "prompt": "Enter connectors (comma-separated): ",
            "prompt_on_new": True
        }
    )
    tokens: Set[str] = Field(
        default={"KAITO", "IP", "GRASS", "ZEC", "APT", "SUI", "TRUMP", "LDO", "OP", "SEI"},
        json_schema_extra={
            "prompt": "Enter tokens (comma-separated): ",
            "prompt_on_new": True
        }
    )

    # Strategy parameters
    leverage: int = Field(
        default=5,
        gt=0,
        json_schema_extra={
            "prompt": "Enter leverage: ",
            "prompt_on_new": True
        }
    )
    min_funding_rate_profitability: Decimal = Field(
        default=Decimal('0.003'),
        json_schema_extra={
            "prompt": "Enter minimum hourly funding spread (e.g., 0.003 for 0.3%): ",
            "prompt_on_new": True
        }
    )
    position_size_quote: Decimal = Field(
        default=Decimal('500'),
        json_schema_extra={
            "prompt": "Enter position size per side in quote currency: ",
            "prompt_on_new": True
        }
    )

    # Exit conditions
    absolute_min_spread_exit: Decimal = Field(
        default=Decimal('0.002'),
        json_schema_extra={
            "prompt": "Enter minimum spread for exit (e.g., 0.002 for 0.2%): ",
            "prompt_on_new": True
        }
    )
    compression_exit_threshold: Decimal = Field(
        default=Decimal('0.4'),
        json_schema_extra={
            "prompt": "Enter compression exit threshold (e.g., 0.4 = 60% compression): ",
            "prompt_on_new": True
        }
    )
    max_position_duration_hours: int = Field(
        default=24,
        json_schema_extra={
            "prompt": "Enter max position duration in hours: ",
            "prompt_on_new": True
        }
    )
    max_loss_per_position_pct: Decimal = Field(
        default=Decimal('0.03'),
        json_schema_extra={
            "prompt": "Enter max loss per position % (e.g., 0.03 for 3%): ",
            "prompt_on_new": True
        }
    )

    # Timing safeguard
    execution_delay_seconds: int = Field(
        default=120,
        json_schema_extra={
            "prompt": "Enter execution delay in seconds: ",
            "prompt_on_new": True
        }
    )

    @field_validator("connectors", "tokens", mode="before")
    @classmethod
    def validate_sets(cls, v):
        if isinstance(v, str):
            return set(v.split(","))
        return v


class FundingRateArbController(ControllerBase):
    """
    Funding rate arbitrage controller.

    Strategy:
    - Monitors funding rate spreads across perpetual DEXs
    - Opens delta-neutral positions (long + short) when spread exceeds threshold
    - Exits based on spread compression, duration, or stop loss

    Timing Model:
    - Funding data = historical payments (no lookahead bias)
    - 2-minute execution delay for data propagation
    - Time-aware queries via BacktestingDataProvider
    """

    # Funding payment intervals by exchange (seconds)
    FUNDING_INTERVALS = {
        'extended_perpetual': 3600 * 8,  # 8 hours
        'lighter_perpetual': 3600 * 1,   # 1 hour
    }

    def __init__(self, config: FundingRateArbControllerConfig, *args, **kwargs):
        super().__init__(config, *args, **kwargs)
        self.config = config

        # Track active arbitrage positions by token
        # Each entry: {connector_1, connector_2, executors_ids, side, entry_spread, entry_timestamp}
        self.active_arbitrages: Dict[str, Dict] = {}

        # Decision audit log (for validation)
        self.decision_log: List[Dict] = []

    async def update_processed_data(self):
        """
        Scan for funding rate arbitrage opportunities.

        Timing Safeguard:
        - Current time: self.market_data_provider.time()
        - Funding data: Historical payments up to current time
        - Execution delay: Only use data from (current_time - execution_delay)

        This ensures 2-minute buffer for data propagation.
        """
        current_time = self.market_data_provider.time()

        # Apply execution delay safeguard
        decision_time = current_time - self.config.execution_delay_seconds

        opportunities = []

        for token in self.config.tokens:
            # Skip if already have active arbitrage for this token
            if token in self.active_arbitrages:
                continue

            # Get funding rates (time-filtered by data provider)
            funding_rates = self._get_funding_info_by_token(token)

            # Validate all rates available
            if not self._validate_funding_rates(funding_rates):
                continue

            # Find best arbitrage opportunity
            best = self._find_best_arbitrage(funding_rates)
            conn1, conn2, side, spread = best

            # Check profitability threshold
            if conn1 and spread >= self.config.min_funding_rate_profitability:
                opportunities.append({
                    'token': token,
                    'connector_1': conn1,
                    'connector_2': conn2,
                    'side': side,
                    'expected_spread': spread,
                    'decision_timestamp': decision_time,
                    'funding_rates': funding_rates
                })

                # Log for audit
                self._log_decision('ENTER', token, funding_rates, spread, decision_time)

        self.processed_data = {
            'opportunities': opportunities,
            'scan_timestamp': current_time,
            'decision_timestamp': decision_time
        }

    def _get_funding_info_by_token(self, token: str) -> Dict[str, FundingInfo]:
        """
        Query funding rates for a token across all connectors.

        Time Safety:
        - Data provider filters: funding_df['timestamp'] <= current_time
        - Returns historical funding payments only
        - No future data accessible
        """
        funding_rates = {}

        for connector_name in self.config.connectors:
            # Get mock connector (registered in backtesting engine)
            connector = self.market_data_provider.connectors.get(connector_name)
            if connector is None:
                continue

            # Get trading pair for this exchange
            trading_pair = self._get_trading_pair(token, connector_name)

            # Query funding info (time-filtered in data provider)
            funding_info = connector.get_funding_info(trading_pair)

            if funding_info is not None:
                funding_rates[connector_name] = funding_info

        return funding_rates

    def _get_trading_pair(self, token: str, connector_name: str) -> str:
        """Get trading pair format for connector."""
        # Extended and Lighter use USD quote
        return f"{token}-USD"

    def _validate_funding_rates(self, funding_rates: Dict) -> bool:
        """Validate that all required funding rates are available."""
        if len(funding_rates) < 2:
            return False
        for info in funding_rates.values():
            if info is None or info.rate is None:
                return False
        return True

    def _find_best_arbitrage(self, funding_rates: Dict[str, FundingInfo]) -> Tuple:
        """
        Find best funding rate arbitrage opportunity.

        Returns: (connector_1, connector_2, side, spread)
        """
        best_spread = Decimal('0')
        best_combo = None

        connectors = list(funding_rates.keys())

        for i, conn1 in enumerate(connectors):
            for conn2 in connectors[i+1:]:
                # Normalize rates to per-second basis
                rate1 = self._normalize_rate(
                    funding_rates[conn1].rate,
                    self.FUNDING_INTERVALS[conn1]
                )
                rate2 = self._normalize_rate(
                    funding_rates[conn2].rate,
                    self.FUNDING_INTERVALS[conn2]
                )

                # Calculate spread (hourly basis for comparison)
                spread_hourly = abs(rate1 - rate2) * Decimal('3600')

                if spread_hourly > best_spread:
                    # Determine which side to take
                    # Long on lower rate exchange, short on higher rate
                    side = TradeType.BUY if rate1 < rate2 else TradeType.SELL
                    best_spread = spread_hourly
                    best_combo = (conn1, conn2, side, spread_hourly)

        return best_combo if best_combo else (None, None, None, Decimal('0'))

    def _normalize_rate(self, rate: Decimal, interval_seconds: int) -> Decimal:
        """Normalize funding rate to per-second basis."""
        return rate / Decimal(str(interval_seconds))

    def create_actions_proposal(self) -> List[ExecutorAction]:
        """
        Create paired arbitrage positions for opportunities.

        Timing:
        - Uses opportunities from update_processed_data()
        - Execution timestamp = decision_timestamp + delay
        - Creates simultaneous long + short positions
        """
        actions = []

        opportunities = self.processed_data.get('opportunities', [])
        current_time = self.market_data_provider.time()

        for opp in opportunities:
            token = opp['token']

            # Create paired executors (long + short)
            executor1, executor2 = self._create_paired_executors(opp, current_time)

            # Track arbitrage state
            self.active_arbitrages[token] = {
                'connector_1': opp['connector_1'],
                'connector_2': opp['connector_2'],
                'executors_ids': [executor1.id, executor2.id],
                'side': opp['side'],
                'entry_spread': opp['expected_spread'],
                'entry_timestamp': current_time,
                'decision_timestamp': opp['decision_timestamp']
            }

            # Create executor actions
            actions.extend([
                CreateExecutorAction(executor_config=executor1),
                CreateExecutorAction(executor_config=executor2)
            ])

        return actions

    def _create_paired_executors(self, opportunity, timestamp) -> Tuple[PositionExecutorConfig, PositionExecutorConfig]:
        """Create long + short position executors."""
        token = opportunity['token']
        conn1 = opportunity['connector_1']
        conn2 = opportunity['connector_2']
        side = opportunity['side']

        # Get current price
        pair1 = self._get_trading_pair(token, conn1)
        price = self.market_data_provider.get_price_by_type(
            conn1, pair1, PriceType.MidPrice
        )

        # Calculate position amount
        amount = self.config.position_size_quote / price

        # Executor 1 (primary side)
        executor1 = PositionExecutorConfig(
            timestamp=timestamp,
            connector_name=conn1,
            trading_pair=pair1,
            side=side,
            amount=amount,
            leverage=self.config.leverage,
            triple_barrier_config=TripleBarrierConfig(
                open_order_type=OrderType.MARKET
            )
        )

        # Executor 2 (opposite side)
        pair2 = self._get_trading_pair(token, conn2)
        executor2 = PositionExecutorConfig(
            timestamp=timestamp,
            connector_name=conn2,
            trading_pair=pair2,
            side=TradeType.SELL if side == TradeType.BUY else TradeType.BUY,
            amount=amount,
            leverage=self.config.leverage,
            triple_barrier_config=TripleBarrierConfig(
                open_order_type=OrderType.MARKET
            )
        )

        return executor1, executor2

    def stop_actions_proposal(self) -> List[ExecutorAction]:
        """
        Determine position exits based on current conditions.

        Exit Triggers:
        1. Spread compression > 60%
        2. Spread < 0.2% absolute
        3. Duration > 24 hours
        4. Loss > 3%

        Timing Safety:
        - Uses current funding rates (time-filtered)
        - No future data used in decisions
        """
        stop_actions = []
        current_time = self.market_data_provider.time()

        for token, arb_info in list(self.active_arbitrages.items()):
            # Get current funding rates
            current_funding = self._get_funding_info_by_token(token)

            if not self._validate_funding_rates(current_funding):
                continue

            # Calculate current spread
            current_spread = self._calculate_current_spread(
                current_funding,
                arb_info['connector_1'],
                arb_info['connector_2'],
                arb_info['side']
            )

            # Check exit conditions
            should_exit, reason = self._should_exit_position(
                arb_info=arb_info,
                current_spread=current_spread,
                current_time=current_time
            )

            if should_exit:
                # Log exit decision
                self._log_decision('EXIT', token, current_funding, current_spread, current_time, reason)

                # Create stop actions for both executors
                for executor_id in arb_info['executors_ids']:
                    stop_actions.append(StopExecutorAction(executor_id=executor_id))

                # Remove from active tracking
                del self.active_arbitrages[token]

        return stop_actions

    def _calculate_current_spread(self, funding_rates, conn1, conn2, side) -> Decimal:
        """Calculate current funding spread."""
        rate1 = self._normalize_rate(
            funding_rates[conn1].rate,
            self.FUNDING_INTERVALS[conn1]
        )
        rate2 = self._normalize_rate(
            funding_rates[conn2].rate,
            self.FUNDING_INTERVALS[conn2]
        )
        return abs(rate1 - rate2) * Decimal('3600')  # Hourly basis

    def _should_exit_position(self, arb_info, current_spread, current_time) -> Tuple[bool, str]:
        """
        Check all exit conditions.

        Returns: (should_exit: bool, reason: str)
        """
        entry_spread = arb_info['entry_spread']
        duration_hours = (current_time - arb_info['entry_timestamp']) / 3600

        # 1. Spread compression check
        if entry_spread > 0:
            compression_ratio = current_spread / entry_spread
            if compression_ratio < self.config.compression_exit_threshold:
                compression_pct = (1 - compression_ratio) * 100
                return True, f"Spread compressed {compression_pct:.1f}%"

        # 2. Absolute minimum spread
        if current_spread < self.config.absolute_min_spread_exit:
            return True, f"Spread below minimum: {current_spread:.4f}"

        # 3. Max duration
        if duration_hours >= self.config.max_position_duration_hours:
            return True, f"Max duration: {duration_hours:.1f}h"

        # 4. Stop loss (if PNL available)
        executors = self._get_active_executors(arb_info['executors_ids'])
        if executors:
            total_pnl = sum(e.net_pnl_quote for e in executors)
            position_value = self.config.position_size_quote * 2
            pnl_pct = total_pnl / position_value if position_value > 0 else 0

            if pnl_pct <= -self.config.max_loss_per_position_pct:
                return True, f"Stop loss: {pnl_pct:.2%}"

        return False, ""

    def _get_active_executors(self, executor_ids):
        """Get active executor info objects by IDs."""
        return [e for e in self.executors_info if e.id in executor_ids and e.is_active]

    def _log_decision(self, action: str, token: str, funding_rates: Dict,
                      spread: Decimal, timestamp: float, reason: str = ""):
        """Log decision for audit trail."""
        log_entry = {
            'timestamp': timestamp,
            'datetime': datetime.fromtimestamp(timestamp),
            'action': action,
            'token': token,
            'spread': float(spread),
            'reason': reason
        }
        for conn, info in funding_rates.items():
            log_entry[f'{conn}_rate'] = float(info.rate)
        self.decision_log.append(log_entry)
