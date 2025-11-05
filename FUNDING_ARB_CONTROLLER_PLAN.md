# Funding Rate Arbitrage Controller - Complete Deployment Plan

## Data Timing Model ✅

**Your funding data represents PAST payments:**
- Timestamp 2024-10-04 20:00:00 = funding PAID at 20:00 for previous period
- This data is immediately available at 20:00
- 2-minute execution delay = data available at 20:00, decision made at 20:02
- **No lookahead bias risk** - using historical payment data ✅

## Complete Implementation Plan

### Phase 1: Create Funding Rate Arbitrage Controller

**File**: `/Users/tdl321/quants-lab/controllers/funding_rate_arb.py` (NEW)

#### 1.1 Controller Configuration

```python
from decimal import Decimal
from typing import Set
from pydantic import Field
from hummingbot.strategy_v2.controllers.controller_base import ControllerConfigBase

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
        description="Primary connector for framework compatibility"
    )
    trading_pair: str = Field(
        default="KAITO-USD",
        description="Primary trading pair for framework compatibility"
    )

    # Multi-connector arbitrage configuration
    connectors: Set[str] = Field(
        default={"extended_perpetual", "lighter_perpetual"},
        description="Connectors to scan for arbitrage opportunities"
    )
    tokens: Set[str] = Field(
        default={"KAITO", "IP", "GRASS", "ZEC", "APT", "SUI", "TRUMP", "LDO", "OP", "SEI"},
        description="Tokens to monitor for funding rate spreads"
    )

    # Strategy parameters
    leverage: int = Field(default=5, gt=0)
    min_funding_rate_profitability: Decimal = Field(
        default=Decimal('0.003'),
        description="Minimum hourly funding spread to enter (0.3%)"
    )
    position_size_quote: Decimal = Field(
        default=Decimal('500'),
        description="Position size per side in quote currency"
    )

    # Exit conditions
    absolute_min_spread_exit: Decimal = Field(
        default=Decimal('0.002'),
        description="Exit if spread falls below this (0.2%)"
    )
    compression_exit_threshold: Decimal = Field(
        default=Decimal('0.4'),
        description="Exit if spread compresses by this ratio (0.4 = 60% compression)"
    )
    max_position_duration_hours: int = Field(
        default=24,
        description="Maximum position duration in hours"
    )
    max_loss_per_position_pct: Decimal = Field(
        default=Decimal('0.03'),
        description="Stop loss percentage (3%)"
    )

    # Timing safeguard
    execution_delay_seconds: int = Field(
        default=120,
        description="Delay after funding payment before execution (2 minutes)"
    )
```

#### 1.2 Controller Implementation

**Key components:**

1. **State Management** - Track active arbitrage positions
2. **Opportunity Scanning** - Find profitable spreads with 2-min delay
3. **Funding Rate Queries** - Time-aware queries to historical data
4. **Arbitrage Detection** - Find best connector pairs
5. **Position Entry** - Create paired long+short executors
6. **Position Exit** - Monitor exit conditions (compression, duration, stop loss)
7. **Helper Methods** - Validation, logging, calculations

### Phase 2: Update Backtesting Script

**File**: `/Users/tdl321/quants-lab/scripts/run_funding_arb_backtest_controller.py` (NEW)

Main steps:
1. Initialize BacktestingEngine (loads your cleaned funding data)
2. Create FundingRateArbControllerConfig
3. Run backtest for Oct 4 - Nov 4, 2024 period
4. Display results and save to CSV

### Phase 3: Validation Test Suite

**File**: `/Users/tdl321/quants-lab/scripts/test_funding_controller_validation.py` (NEW)

Tests:
1. Funding time filtering - verify only past data used
2. Execution delay - verify 2-min delay applied
3. Spread calculations - verify no future data in calculations

### Phase 4: Controller Module Initialization

**File**: `/Users/tdl321/quants-lab/controllers/__init__.py` (UPDATE)

Export the new controller classes.

## Implementation Checklist

### Pre-Implementation
- [x] Understand data timing model (funding = past payments)
- [x] Define execution delay (2 minutes)
- [x] Review lookahead bias risks
- [x] Plan controller architecture

### Implementation Steps
1. **Create controller** (`controllers/funding_rate_arb.py`)
   - Controller config class
   - Controller implementation
   - Opportunity scanning with 2-min delay
   - Position entry/exit logic
   - Helper methods

2. **Create backtest script** (`scripts/run_funding_arb_backtest_controller.py`)
   - Initialize engine
   - Configure controller
   - Run backtest
   - Display results

3. **Create validation tests** (`scripts/test_funding_controller_validation.py`)
   - Test time filtering
   - Test execution delay
   - Test spread calculations

4. **Update module init** (`controllers/__init__.py`)
   - Export controller classes

### Testing & Validation
1. Run validation tests:
   ```bash
   python scripts/test_funding_controller_validation.py
   ```

2. Run backtest:
   ```bash
   python scripts/run_funding_arb_backtest_controller.py
   ```

3. Review results:
   - Check total positions
   - Verify win rate
   - Analyze PNL by token
   - Review decision timing in logs

### Post-Implementation
- [ ] Analyze backtest results
- [ ] Parameter sensitivity analysis
- [ ] Compare different configurations
- [ ] Document findings

## Expected Outcomes

### Performance Metrics
```
Total Arbitrage Positions: ~150-200 (paired long+short)
Win Rate: ~55-65% (expected for funding arb)
Total PNL: Depends on spread conditions
Sharpe Ratio: To be measured
Max Drawdown: To be measured
```

### Timing Verification
```
✅ All funding queries use data from timestamp <= current_time
✅ 2-minute execution delay applied
✅ No lookahead bias detected
✅ Decision timestamps precede action timestamps
```

### File Outputs
```
backtest_results_funding_arb_controller.csv - Detailed executor results
```

## Architecture: No Lookahead Bias

### Framework Time Safety (Built-in)

1. **Time stepping** (backtesting_engine_base.py:143):
   ```python
   for i, row in processed_features.iterrows():
       self.controller.market_data_provider._time = row["timestamp"]  # Set current time
       for action in self.controller.determine_executor_actions():    # Make decisions
   ```

2. **Funding data filtering** (backtesting_data_provider.py:271):
   ```python
   current_time = self._time
   historical_data = funding_df[funding_df['timestamp'] <= current_time]
   latest = historical_data.iloc[-1]  # Most recent data at or before current time
   ```

3. **Mock connectors** delegate to time-aware data provider

### Additional Safeguards

1. **2-minute execution delay** - Conservative buffer for data propagation
2. **Decision audit logging** - Track all decisions for verification
3. **Timestamp validation** - Assert decision time <= execution time
4. **Validation test suite** - Automated checks for lookahead bias

## Data Flow

```
Controller.update_processed_data()
    ↓
current_time = self.market_data_provider.time()  # Backtest timestamp
decision_time = current_time - 120  # Apply 2-min delay
    ↓
for token in tokens:
    funding_rates = _get_funding_info_by_token(token)
        ↓
    connector.get_funding_info(trading_pair)
        ↓
    data_provider.get_funding_info(connector, pair)
        ↓
    funding_df[funding_df['timestamp'] <= current_time]  # Filter to past
        ↓
    return latest funding rate (PAST DATA ONLY)
```

## Notes

**Data Safety:**
- Funding data represents PAST payments ✅
- 2-minute execution delay for data propagation ✅
- No lookahead bias in framework ✅

**Framework Compatibility:**
- Controller extends ControllerBase ✅
- Works with existing BacktestingEngine ✅
- Uses mock perpetual connectors ✅

**No Jupyter Required:**
- Pure Python CLI scripts ✅
- Instant execution ✅
- Easy to version control ✅

## Key Implementation Details

### Funding Rate Normalization
Extended and Lighter have different funding intervals:
- Extended: 8-hour intervals (rate / 28800 seconds)
- Lighter: 1-hour intervals (rate / 3600 seconds)

Normalize to per-second basis, then compare on hourly basis for consistency.

### Paired Position Tracking
Each arbitrage is TWO executors:
- Executor 1: Long/Short on connector_1
- Executor 2: Opposite side on connector_2

Track both executor IDs together, exit both simultaneously.

### Exit Logic Priority
1. Spread compression > 60%
2. Spread < 0.2% absolute
3. Duration > 24 hours
4. Loss > 3%

Check in order, exit on first trigger.
