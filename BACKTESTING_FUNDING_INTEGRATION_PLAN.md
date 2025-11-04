# Funding Rate Backtesting Integration Plan (Option A)

**Date**: 2025-11-04
**Status**: Planning
**Approach**: Extend Hummingbot BacktestingDataProvider

---

## 🎯 Objective

Integrate our 31 days of historical funding rate data (Extended + Lighter) into Hummingbot's backtesting framework to enable simulation of the `v2_funding_rate_arb.py` strategy.

**Key Goal**: Make hummingbot's backtesting engine **time-aware** for funding rates, so strategies can query historical funding data at any timestamp during backtest simulation.

---

## 📊 Current State Analysis

### What We Have ✅

1. **Historical Funding Data**
   - `app/data/cache/funding/raw/extended_historical_31d.parquet` (7,433 records)
   - `app/data/cache/funding/raw/lighter_historical_31d.parquet` (7,440 records)
   - Date range: Oct 4 - Nov 4, 2025
   - All 10 target tokens: KAITO, IP, GRASS, ZEC, APT, SUI, TRUMP, LDO, OP, SEI

2. **Hummingbot Backtesting Framework**
   - Location: `/Users/tdl321/hummingbot/hummingbot/strategy_v2/backtesting/`
   - `BacktestingEngine` (quants-lab wrapper)
   - `BacktestingEngineBase` (hummingbot core)
   - `BacktestingDataProvider` (data abstraction layer)

3. **Funding Rate Arbitrage Strategy**
   - File: `/Users/tdl321/hummingbot/scripts/v2_funding_rate_arb.py`
   - Uses: `connector.get_funding_info(trading_pair)`
   - Returns: `FundingInfo` objects (rate, next_funding_timestamp, mark_price, index_price)

### What's Missing ❌

1. **No funding rate support in BacktestingDataProvider**
   - Has: `candles_feeds` dict for price data
   - Missing: `funding_feeds` dict for funding data
   - Missing: `get_funding_info()` method with timestamp awareness

2. **No Extended/Lighter perpetual connectors**
   - Strategy references: `extended_perpetual`, `lighter_perpetual`
   - Connectors don't exist in hummingbot repo
   - Need mock/simulated versions for backtesting

3. **No funding data loader**
   - BacktestingEngine loads candles from parquet
   - No equivalent loader for funding rate parquet files

---

## 🏗️ Architecture Design

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     BACKTESTING ENGINE                          │
│  (quants-lab/core/backtesting/engine.py)                        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│              BACKTESTING ENGINE BASE (Hummingbot)               │
│  - Runs strategy simulation                                     │
│  - Steps through time (start → end)                             │
│  - Calls strategy methods at each timestamp                     │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│         BACKTESTING DATA PROVIDER (Enhanced)                    │
│                                                                  │
│  EXISTING:                                                       │
│  • candles_feeds = {...}      # Pre-loaded price data           │
│  • get_price_by_type()        # Returns price at backtest time  │
│  • _time                      # Current backtest timestamp      │
│                                                                  │
│  NEW (TO ADD):                                                   │
│  • funding_feeds = {...}      # Pre-loaded funding data ← ADD   │
│  • get_funding_info()         # Returns funding at time ← ADD   │
│  • _load_funding_cache()     # Load parquet files ← ADD         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│              MOCK PERPETUAL CONNECTORS (New)                    │
│                                                                  │
│  ExtendedPerpetualBacktestConnector:                            │
│    def get_funding_info(trading_pair):                          │
│      return data_provider.get_funding_info(                     │
│        "extended", trading_pair, current_time                   │
│      )                                                           │
│                                                                  │
│  LighterPerpetualBacktestConnector:                             │
│    def get_funding_info(trading_pair):                          │
│      return data_provider.get_funding_info(                     │
│        "lighter", trading_pair, current_time                    │
│      )                                                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│                   FUNDING RATE STRATEGY                         │
│  (scripts/v2_funding_rate_arb.py)                               │
│                                                                  │
│  def get_funding_info_by_token(token):                          │
│    for connector in connectors:                                 │
│      funding_info = connector.get_funding_info(trading_pair)    │
│      # ↑ Now returns HISTORICAL data at backtest timestamp      │
└─────────────────────────────────────────────────────────────────┘
```

### Data Format in BacktestingDataProvider

```python
# Structure of funding_feeds dict
funding_feeds = {
    "extended_KAITO-USD": pd.DataFrame({
        "timestamp": [1696435200, 1696438800, ...],  # Unix timestamps
        "funding_rate": [0.0001, -0.0002, ...],
        "mark_price": [1.25, 1.26, ...],
        "index_price": [1.24, 1.25, ...],
        "next_funding_timestamp": [1696438800, 1696442400, ...]
    }),
    "lighter_KAITO-USD": pd.DataFrame({...}),
    ...
}
```

---

## 📝 Implementation Plan

### Phase 1: Extend BacktestingDataProvider (Core Changes)

**Location**: Fork or extend `hummingbot/strategy_v2/backtesting/backtesting_data_provider.py`

#### Step 1.1: Add Funding Feeds Storage
```python
class BacktestingDataProvider(MarketDataProvider):
    def __init__(self, connectors: Dict[str, ConnectorBase]):
        super().__init__(connectors)
        self.start_time = None
        self.end_time = None
        self.prices = {}
        self._time = None
        self.trading_rules = {}
        self.candles_feeds = {}
        self.funding_feeds = {}  # ← ADD THIS
```

**File**: Create `/Users/tdl321/quants-lab/core/backtesting/enhanced_data_provider.py`
**Effort**: 5 minutes
**Lines**: ~5

---

#### Step 1.2: Add Funding Data Loader
```python
def _load_funding_cache(self, funding_path: Path):
    """
    Load funding rate data from parquet files.

    Expected file format:
    - Columns: timestamp, exchange, base, quote, funding_rate
    - Files: extended_historical_31d.parquet, lighter_historical_31d.parquet
    """
    if not funding_path.exists():
        logger.warning(f"Funding directory {funding_path} does not exist.")
        return

    all_files = list(funding_path.glob("*.parquet"))

    for file in all_files:
        try:
            logger.info(f"Loading funding data from {file.name}")
            df = pd.read_parquet(file)

            # Group by exchange and trading pair
            for exchange in df['exchange'].unique():
                for base in df['base'].unique():
                    quote = df['quote'].iloc[0] if 'quote' in df.columns else 'USD'

                    # Filter data for this exchange-pair
                    pair_df = df[
                        (df['exchange'] == exchange) &
                        (df['base'] == base)
                    ].copy()

                    # Sort by timestamp
                    pair_df = pair_df.sort_values('timestamp').reset_index(drop=True)

                    # Create feed key: "extended_KAITO-USD"
                    connector_name = f"{exchange}_perpetual"
                    trading_pair = f"{base}-{quote}"
                    feed_key = f"{connector_name}_{trading_pair}"

                    # Store in funding_feeds
                    self.funding_feeds[feed_key] = pair_df

                    logger.info(
                        f"  ✅ Loaded {len(pair_df)} funding records for {feed_key}"
                    )

        except Exception as e:
            logger.error(f"Error loading funding data from {file}: {e}")
```

**File**: `/Users/tdl321/quants-lab/core/backtesting/enhanced_data_provider.py`
**Effort**: 1 hour
**Lines**: ~50

---

#### Step 1.3: Add get_funding_info() Method
```python
def get_funding_info(
    self,
    connector_name: str,
    trading_pair: str
) -> Optional[FundingInfo]:
    """
    Get funding info at the current backtest timestamp.

    Args:
        connector_name: e.g., "extended_perpetual"
        trading_pair: e.g., "KAITO-USD"

    Returns:
        FundingInfo object with historical data, or None if not available
    """
    from hummingbot.core.data_type.funding_info import FundingInfo
    from decimal import Decimal

    # Get funding feed for this connector-pair
    feed_key = f"{connector_name}_{trading_pair}"
    funding_df = self.funding_feeds.get(feed_key)

    if funding_df is None or funding_df.empty:
        logger.warning(f"No funding data for {feed_key}")
        return None

    # Get current backtest time
    current_time = self._time

    # Find most recent funding rate at or before current time
    # (forward-fill logic)
    historical_data = funding_df[funding_df['timestamp'] <= current_time]

    if historical_data.empty:
        logger.warning(
            f"No funding data for {feed_key} at timestamp {current_time}"
        )
        return None

    # Get most recent record
    latest = historical_data.iloc[-1]

    # Calculate next funding timestamp
    # Assume hourly funding (3600 seconds)
    funding_interval = 3600
    next_funding = latest['timestamp'] + funding_interval

    # Get mark/index price from candles (if available)
    # Otherwise use placeholder values
    mark_price = self.get_price_by_type(
        connector_name, trading_pair, PriceType.MidPrice
    )
    index_price = mark_price  # Simplified - could be more sophisticated

    # Create FundingInfo object
    funding_info = FundingInfo(
        trading_pair=trading_pair,
        index_price=Decimal(str(index_price)),
        mark_price=Decimal(str(mark_price)),
        next_funding_utc_timestamp=int(next_funding),
        rate=Decimal(str(latest['funding_rate']))
    )

    return funding_info
```

**File**: `/Users/tdl321/quants-lab/core/backtesting/enhanced_data_provider.py`
**Effort**: 1 hour
**Lines**: ~60

---

### Phase 2: Update BacktestingEngine to Load Funding Data

**Location**: `/Users/tdl321/quants-lab/core/backtesting/engine.py`

#### Step 2.1: Import Enhanced Data Provider
```python
from core.backtesting.enhanced_data_provider import EnhancedBacktestingDataProvider
```

#### Step 2.2: Update Initialization
```python
class BacktestingEngine:
    def __init__(self, load_cached_data: bool = True, custom_backtester: Optional[BacktestingEngineBase] = None):
        # Use enhanced data provider
        enhanced_provider = EnhancedBacktestingDataProvider({})

        self._bt_engine = custom_backtester if custom_backtester is not None else BacktestingEngineBase()

        # Replace data provider with enhanced version
        self._bt_engine.backtesting_data_provider = enhanced_provider

        if load_cached_data:
            self._load_candles_cache()
            self._load_funding_cache()  # ← ADD THIS
```

#### Step 2.3: Add Funding Cache Loader
```python
def _load_funding_cache(self):
    """Load funding rate data from parquet files."""
    from core.data_paths import data_paths

    # Use centralized data paths
    funding_path = data_paths.project_root / 'app' / 'data' / 'cache' / 'funding' / 'raw'

    if not funding_path.exists():
        logger.warning(f"Funding directory {funding_path} does not exist.")
        return

    # Call data provider's loader
    self._bt_engine.backtesting_data_provider._load_funding_cache(funding_path)

    logger.info("✅ Funding cache loaded successfully")
```

**File**: `/Users/tdl321/quants-lab/core/backtesting/engine.py`
**Effort**: 30 minutes
**Lines**: ~30

---

### Phase 3: Create Mock Perpetual Connectors

**Purpose**: Provide connector objects that return historical funding data during backtesting

**Location**: `/Users/tdl321/quants-lab/core/backtesting/mock_connectors.py`

```python
"""
Mock Perpetual Connectors for Backtesting

These connectors simulate Extended and Lighter perpetual exchanges
using pre-loaded historical data.
"""

from decimal import Decimal
from typing import Optional
from hummingbot.core.data_type.funding_info import FundingInfo
from hummingbot.core.data_type.common import PositionMode, OrderType, TradeType, PositionAction
from hummingbot.connector.utils import TradeFeeSchema


class BacktestPerpetualConnectorBase:
    """
    Base class for backtesting perpetual connectors.

    Provides minimal interface needed by v2_funding_rate_arb strategy.
    """

    def __init__(self, connector_name: str, data_provider):
        self.connector_name = connector_name
        self.data_provider = data_provider
        self._position_mode = PositionMode.ONEWAY
        self._leverage = {}

    def set_position_mode(self, position_mode: PositionMode):
        """Set position mode (ONEWAY or HEDGE)."""
        self._position_mode = position_mode

    def set_leverage(self, trading_pair: str, leverage: int):
        """Set leverage for a trading pair."""
        self._leverage[trading_pair] = leverage

    def get_funding_info(self, trading_pair: str) -> Optional[FundingInfo]:
        """
        Get historical funding info at current backtest timestamp.

        Delegates to BacktestingDataProvider which has time awareness.
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
    ):
        """
        Return trading fee for the exchange.

        Extended: 0.02% maker, 0.05% taker
        Lighter: 0.01% maker, 0.03% taker
        """
        # Return fee schema (simplified)
        if self.connector_name == "extended_perpetual":
            fee_pct = Decimal("0.0002") if is_maker else Decimal("0.0005")
        elif self.connector_name == "lighter_perpetual":
            fee_pct = Decimal("0.0001") if is_maker else Decimal("0.0003")
        else:
            fee_pct = Decimal("0.0005")  # Default

        return TradeFeeSchema(
            maker_percent_fee_decimal=fee_pct if is_maker else Decimal("0"),
            taker_percent_fee_decimal=fee_pct if not is_maker else Decimal("0"),
            percent_fee_token=quote_currency,
            buy_percent_fee_deduction_from_returns=True
        )


class ExtendedPerpetualBacktestConnector(BacktestPerpetualConnectorBase):
    """Mock Extended Perpetual connector for backtesting."""

    def __init__(self, data_provider):
        super().__init__("extended_perpetual", data_provider)


class LighterPerpetualBacktestConnector(BacktestPerpetualConnectorBase):
    """Mock Lighter Perpetual connector for backtesting."""

    def __init__(self, data_provider):
        super().__init__("lighter_perpetual", data_provider)
```

**File**: `/Users/tdl321/quants-lab/core/backtesting/mock_connectors.py`
**Effort**: 1.5 hours
**Lines**: ~100

---

### Phase 4: Register Mock Connectors in BacktestingEngine

**Location**: `/Users/tdl321/quants-lab/core/backtesting/engine.py`

```python
def _register_mock_connectors(self):
    """
    Register mock perpetual connectors for backtesting.

    These connectors return historical funding data during simulation.
    """
    from core.backtesting.mock_connectors import (
        ExtendedPerpetualBacktestConnector,
        LighterPerpetualBacktestConnector
    )

    data_provider = self._bt_engine.backtesting_data_provider

    # Create mock connectors
    extended_connector = ExtendedPerpetualBacktestConnector(data_provider)
    lighter_connector = LighterPerpetualBacktestConnector(data_provider)

    # Register in data provider's connectors dict
    # (This allows strategy to access them)
    data_provider.connectors["extended_perpetual"] = extended_connector
    data_provider.connectors["lighter_perpetual"] = lighter_connector

    logger.info("✅ Registered mock perpetual connectors: extended, lighter")
```

Update `__init__`:
```python
def __init__(self, load_cached_data: bool = True, custom_backtester: Optional[BacktestingEngineBase] = None):
    # ... existing code ...

    if load_cached_data:
        self._load_candles_cache()
        self._load_funding_cache()
        self._register_mock_connectors()  # ← ADD THIS
```

**Effort**: 30 minutes
**Lines**: ~30

---

### Phase 5: Create Backtesting Notebook

**Location**: `/Users/tdl321/quants-lab/research_notebooks/eda_strategies/funding_rate_arb/02_backtest_with_historical_data.ipynb`

```python
"""
Funding Rate Arbitrage Backtest - Extended + Lighter Historical Data

This notebook runs the v2_funding_rate_arb strategy on 31 days of
historical funding rate data from Extended and Lighter DEXs.
"""

# Cell 1: Imports
import warnings
warnings.filterwarnings("ignore")

import sys
sys.path.append('/Users/tdl321/quants-lab')
sys.path.append('/Users/tdl321/hummingbot')

from core.backtesting import BacktestingEngine
from scripts.v2_funding_rate_arb import FundingRateArbitrageConfig
import datetime
from decimal import Decimal
import pandas as pd
import plotly.express as px

# Cell 2: Initialize Backtesting Engine
print("Initializing backtesting engine...")
backtesting = BacktestingEngine(load_cached_data=True)
print("✅ Engine initialized")
print(f"   Funding feeds loaded: {len(backtesting._bt_engine.backtesting_data_provider.funding_feeds)}")

# Cell 3: Configure Strategy
config = FundingRateArbitrageConfig(
    connectors={"extended_perpetual", "lighter_perpetual"},
    tokens={"KAITO", "IP", "GRASS", "ZEC", "APT", "SUI", "TRUMP", "LDO", "OP", "SEI"},
    leverage=5,
    min_funding_rate_profitability=Decimal('0.003'),  # 0.3% hourly
    position_size_quote=Decimal('500'),  # $500 per side
    absolute_min_spread_exit=Decimal('0.002'),  # 0.2%
    compression_exit_threshold=Decimal('0.4'),  # 60% compression
    max_position_duration_hours=24,
    max_loss_per_position_pct=Decimal('0.03'),  # 3% stop loss
    trade_profitability_condition_to_enter=False
)

print("Strategy Configuration:")
print(f"  Exchanges: extended_perpetual, lighter_perpetual")
print(f"  Tokens: {len(config.tokens)}")
print(f"  Min Spread: {config.min_funding_rate_profitability:.2%}")
print(f"  Position Size: ${config.position_size_quote} per side")
print(f"  Leverage: {config.leverage}x")

# Cell 4: Set Backtest Period
# Use the 31-day period we have data for
start = int(datetime.datetime(2024, 10, 4).timestamp())
end = int(datetime.datetime(2024, 11, 4).timestamp())
backtesting_resolution = "1h"  # Hourly resolution

print(f"Backtest Period:")
print(f"  Start: {datetime.datetime.fromtimestamp(start)}")
print(f"  End: {datetime.datetime.fromtimestamp(end)}")
print(f"  Duration: 31 days")
print(f"  Resolution: {backtesting_resolution}")

# Cell 5: Run Backtest
print("\n" + "="*80)
print("RUNNING BACKTEST")
print("="*80 + "\n")

backtesting_result = await backtesting.run_backtesting(
    config,
    start,
    end,
    backtesting_resolution,
    trade_cost=0.0005  # 0.05% trading fee
)

print("\n✅ Backtest completed successfully!")

# Cell 6: Display Results Summary
print("\n" + "="*80)
print("BACKTEST RESULTS SUMMARY")
print("="*80)
print(backtesting_result.get_results_summary())

# Cell 7: Visualize Results
backtesting_result.get_backtesting_figure()

# ... (rest of analysis cells similar to existing notebook)
```

**File**: `/Users/tdl321/quants-lab/research_notebooks/eda_strategies/funding_rate_arb/02_backtest_with_historical_data.ipynb`
**Effort**: 2 hours
**Lines**: ~500

---

## 🧪 Testing Strategy

### Unit Tests

**File**: `/Users/tdl321/quants-lab/tests/test_enhanced_data_provider.py`

```python
import pytest
import pandas as pd
from core.backtesting.enhanced_data_provider import EnhancedBacktestingDataProvider

def test_load_funding_cache():
    """Test loading funding data from parquet files."""
    provider = EnhancedBacktestingDataProvider({})
    provider._load_funding_cache(Path('app/data/cache/funding/raw'))

    assert len(provider.funding_feeds) > 0
    assert "extended_perpetual_KAITO-USD" in provider.funding_feeds

def test_get_funding_info():
    """Test retrieving funding info at specific timestamp."""
    provider = EnhancedBacktestingDataProvider({})
    provider._load_funding_cache(Path('app/data/cache/funding/raw'))
    provider._time = 1696435200  # Set backtest time

    funding_info = provider.get_funding_info("extended_perpetual", "KAITO-USD")

    assert funding_info is not None
    assert funding_info.rate is not None
    assert funding_info.next_funding_utc_timestamp > provider._time
```

**Effort**: 1 hour

---

### Integration Tests

**File**: `/Users/tdl321/quants-lab/tests/test_backtest_integration.py`

```python
def test_backtest_with_funding_data():
    """Test full backtest execution with funding data."""
    from core.backtesting import BacktestingEngine
    from scripts.v2_funding_rate_arb import FundingRateArbitrageConfig
    import datetime

    # Initialize engine
    engine = BacktestingEngine(load_cached_data=True)

    # Verify funding data loaded
    assert len(engine._bt_engine.backtesting_data_provider.funding_feeds) > 0

    # Configure strategy
    config = FundingRateArbitrageConfig(
        connectors={"extended_perpetual", "lighter_perpetual"},
        tokens={"KAITO"},
        leverage=5,
        min_funding_rate_profitability=Decimal('0.003'),
        position_size_quote=Decimal('500'),
    )

    # Run short backtest (1 day)
    start = int(datetime.datetime(2024, 10, 4).timestamp())
    end = int(datetime.datetime(2024, 10, 5).timestamp())

    result = await engine.run_backtesting(config, start, end, "1h")

    # Verify result
    assert result is not None
    assert len(result.executors_df) >= 0  # May have 0 trades if no opportunities
```

**Effort**: 1 hour

---

## 📋 Implementation Checklist

### Phase 1: Core Data Provider (3 hours)
- [ ] Create `enhanced_data_provider.py`
- [ ] Add `funding_feeds` dict
- [ ] Implement `_load_funding_cache()`
- [ ] Implement `get_funding_info()`
- [ ] Test with sample data

### Phase 2: Engine Integration (1 hour)
- [ ] Update `engine.py` imports
- [ ] Add `_load_funding_cache()` method
- [ ] Call funding loader in `__init__`
- [ ] Test funding cache loading

### Phase 3: Mock Connectors (2 hours)
- [ ] Create `mock_connectors.py`
- [ ] Implement `BacktestPerpetualConnectorBase`
- [ ] Implement `ExtendedPerpetualBacktestConnector`
- [ ] Implement `LighterPerpetualBacktestConnector`
- [ ] Add fee calculation logic

### Phase 4: Connector Registration (1 hour)
- [ ] Add `_register_mock_connectors()` to engine
- [ ] Call registration in `__init__`
- [ ] Test connector access from strategy

### Phase 5: Backtesting Notebook (2 hours)
- [ ] Create `02_backtest_with_historical_data.ipynb`
- [ ] Add configuration cells
- [ ] Add execution cells
- [ ] Add analysis cells
- [ ] Add visualization cells

### Phase 6: Testing (2 hours)
- [ ] Write unit tests for data provider
- [ ] Write integration tests
- [ ] Run manual test backtest
- [ ] Validate results

**Total Estimated Effort**: 11 hours

---

## 📈 Expected Outcomes

### Immediate Deliverables

1. **Working Backtest System**
   - Can run v2_funding_rate_arb strategy on 31 days of historical data
   - Simulates Extended + Lighter funding arbitrage
   - Generates PNL and performance metrics

2. **Performance Insights**
   - Total PNL over 31 days
   - Number of arbitrage positions opened
   - Win rate and profit factor
   - Best/worst performing tokens
   - Optimal entry/exit thresholds

3. **Reusable Framework**
   - Can backtest any funding rate strategy
   - Can add more exchanges (just add parquet files)
   - Can extend time period as more data collected

### Success Metrics

✅ **Must Have**:
- Backtest runs without errors
- Funding rates correctly loaded for all 10 tokens
- Strategy opens positions when spreads exceed threshold
- PNL calculation includes funding payments + trading fees

✅ **Should Have**:
- At least 10 arbitrage positions opened over 31 days
- Positive total PNL (proves strategy viability)
- Detailed position-level metrics

✅ **Nice to Have**:
- Parameter sensitivity analysis
- Comparison with manual calculations
- Performance attribution by token

---

## 🚨 Potential Issues & Mitigations

### Issue 1: Missing Price Data
**Problem**: Mock connectors need mark/index prices, but we only have funding rates
**Mitigation**:
- Use candles data if available
- Otherwise, use placeholder prices (funding arb is mostly funding-driven)
- Could download historical price data from Extended API if needed

### Issue 2: Strategy Expects Real Connectors
**Problem**: v2_funding_rate_arb might call methods we haven't mocked
**Mitigation**:
- Start with minimal connector interface
- Add methods as errors occur
- Most critical: `get_funding_info()`, `set_leverage()`, `get_fee()`

### Issue 3: Funding Payment Tracking
**Problem**: Strategy tracks actual funding payments, but we're in backtest
**Mitigation**:
- Backtesting framework simulates funding payment events
- Ensure `FundingPaymentCompletedEvent` is fired at correct intervals

### Issue 4: Data Gaps
**Problem**: Extended has 7 missing GRASS records (99% vs 100% complete)
**Mitigation**:
- Forward-fill funding rates (acceptable for 1-hour gaps)
- Log warnings for missing data
- Exclude GRASS from backtest if problematic

---

## 🎯 Next Steps

### Immediate (Today)
1. Create `enhanced_data_provider.py` skeleton
2. Implement `_load_funding_cache()`
3. Test funding data loading

### Tomorrow
1. Implement `get_funding_info()`
2. Create mock connectors
3. Integrate with BacktestingEngine

### Day 3
1. Create backtesting notebook
2. Run first test backtest
3. Debug and iterate

### Day 4
1. Analyze results
2. Write documentation
3. Optimize parameters

---

## 📚 References

- Hummingbot Backtesting Docs: https://docs.hummingbot.org/v2-strategies/backtesting/
- v2_funding_rate_arb strategy: `/Users/tdl321/hummingbot/scripts/v2_funding_rate_arb.py`
- Our data sources: `/Users/tdl321/quants-lab/core/data_sources/`
- Historical data: `/Users/tdl321/quants-lab/app/data/cache/funding/raw/`
- Funding info structure: `/Users/tdl321/hummingbot/hummingbot/core/data_type/funding_info.py`

---

## ✅ Conclusion

This plan provides a **clean, maintainable integration** of our historical funding rate data into Hummingbot's backtesting framework. By extending the `BacktestingDataProvider` and creating lightweight mock connectors, we can:

- ✅ Use the full v2_funding_rate_arb strategy without modification
- ✅ Leverage Hummingbot's robust backtesting engine
- ✅ Maintain clean separation of concerns
- ✅ Enable future extensions (more exchanges, longer periods)

**Estimated completion**: 11 hours (2-3 days of focused work)

**Ready to start implementation!** 🚀
