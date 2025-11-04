# Modular Data Source Architecture - Implementation Plan

**Date**: 2025-11-04
**Goal**: Add Extended/Lighter API data sources with minimal code duplication

---

## 🎯 Design Principles

1. **Reuse existing infrastructure** (storage, data provider, collector)
2. **Abstract data sources** behind common interface
3. **Minimal code duplication**
4. **Single responsibility** per module
5. **Easy to add new data sources** in future

---

## 🏗️ Modular Architecture

### **Current System (Works)**
```
FundingRateCollector (orchestration)
    ↓
CoinGeckoFundingDataSource (API client)
    ↓
Parquet Storage (data/cache/funding/raw/)
    ↓
FundingRateBacktestDataProvider (reader)
```

### **New Modular System (Proposed)**
```
FundingRateCollector (orchestration) - NO CHANGES NEEDED
    ↓
BaseFundingDataSource (abstract interface) - NEW
    ├─→ CoinGeckoFundingDataSource (existing, slight refactor)
    ├─→ ExtendedFundingDataSource (new, historical bulk download)
    └─→ LighterFundingDataSource (new, future)
    ↓
Parquet Storage (data/cache/funding/raw/) - NO CHANGES
    ↓
FundingRateBacktestDataProvider (reader) - NO CHANGES
```

**Key Insight**: Only need to create new data source classes that conform to existing interface!

---

## 📦 Component Design

### **1. Base Interface (Abstract Class)**

**File**: `/Users/tdl321/quants-lab/core/data_sources/base_funding_source.py` (NEW)

**Purpose**: Define common interface all data sources must implement

```python
from abc import ABC, abstractmethod
from typing import List, Optional
import pandas as pd

class BaseFundingDataSource(ABC):
    """
    Abstract base class for funding rate data sources.

    All data sources (CoinGecko, Extended, Lighter) must implement these methods
    to ensure they work with FundingRateCollector.
    """

    @abstractmethod
    async def start(self):
        """Initialize connection/session."""
        pass

    @abstractmethod
    async def stop(self):
        """Close connection/session."""
        pass

    @abstractmethod
    async def get_funding_rates(
        self,
        exchange: str,
        tokens: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Fetch funding rates for an exchange.

        Returns:
            DataFrame with standardized schema:
            - timestamp: int
            - exchange: str
            - base: str (token symbol)
            - target: str (quote currency)
            - funding_rate: float
            - index: float (price)
            ... other fields
        """
        pass

    @abstractmethod
    async def get_funding_rates_multi_exchange(
        self,
        exchanges: List[str],
        tokens: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """Fetch from multiple exchanges, return combined DataFrame."""
        pass

    def calculate_spreads(self, funding_df: pd.DataFrame) -> pd.DataFrame:
        """Calculate spreads (common implementation for all sources)."""
        # Shared logic - can be in base class
        pass
```

**Effort**: 30 minutes

---

### **2. Extended API Data Source**

**File**: `/Users/tdl321/quants-lab/core/data_sources/extended_funding.py` (NEW)

**Purpose**: Fetch historical + current funding rates from Extended API

```python
from core.data_sources.base_funding_source import BaseFundingDataSource
import aiohttp
import pandas as pd
from typing import List, Optional
from datetime import datetime
import time

class ExtendedFundingDataSource(BaseFundingDataSource):
    """
    Extended DEX API client for funding rate data.

    Features:
    - Historical data with time range (startTime, endTime)
    - Up to 10,000 records per request
    - Pagination support
    """

    BASE_URL = "https://api.extended.exchange"

    def __init__(self, user_agent: str = "backtest"):
        self.user_agent = user_agent
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        """Create HTTP session."""
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent
        }
        self._session = aiohttp.ClientSession(headers=headers)

    async def stop(self):
        """Close HTTP session."""
        if self._session:
            await self._session.close()

    async def get_historical_funding_rates(
        self,
        market: str,           # e.g., "KAITO-USD"
        start_time: int,       # Unix timestamp
        end_time: int,         # Unix timestamp
        limit: int = 10000
    ) -> pd.DataFrame:
        """
        Fetch historical funding rates from Extended.

        Endpoint: GET /api/v1/info/{market}/funding
        """
        url = f"{self.BASE_URL}/api/v1/info/{market}/funding"
        params = {
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }

        async with self._session.get(url, params=params) as response:
            response.raise_for_status()
            data = await response.json()

        # Parse response to standardized format
        records = []
        for item in data:
            records.append({
                'timestamp': item['T'],
                'exchange': 'extended',
                'base': market.split('-')[0],  # Extract token from "KAITO-USD"
                'target': market.split('-')[1],
                'funding_rate': item['f'],
                'index': 0,  # Not provided by Extended, use 0 or fetch separately
                'symbol': market,
                # Add other fields as needed
            })

        return pd.DataFrame(records)

    async def get_funding_rates(
        self,
        exchange: str,  # Not used (Extended only has 'extended')
        tokens: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Get current funding rates (most recent snapshot).

        For compatibility with FundingRateCollector interface.
        """
        if not tokens:
            # Get all markets from Extended
            tokens = await self._get_available_tokens()

        # For each token, get most recent funding rate
        dfs = []
        current_time = int(time.time())
        lookback = 3600  # Look back 1 hour

        for token in tokens:
            market = f"{token}-USD"  # Assuming USD markets
            df = await self.get_historical_funding_rates(
                market=market,
                start_time=current_time - lookback,
                end_time=current_time,
                limit=1  # Only most recent
            )
            if not df.empty:
                dfs.append(df)

        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    async def get_funding_rates_multi_exchange(
        self,
        exchanges: List[str],
        tokens: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """For Extended, only one exchange, so same as get_funding_rates."""
        return await self.get_funding_rates("extended", tokens)

    async def get_available_markets(self) -> List[str]:
        """
        Get list of all markets on Extended.

        Endpoint: GET /api/v1/info/markets
        """
        url = f"{self.BASE_URL}/api/v1/info/markets"

        async with self._session.get(url) as response:
            response.raise_for_status()
            data = await response.json()

        # Extract market names
        markets = [market['market'] for market in data]
        return markets

    async def _get_available_tokens(self) -> List[str]:
        """Extract token symbols from markets."""
        markets = await self.get_available_markets()
        tokens = list(set([m.split('-')[0] for m in markets]))
        return tokens

    async def bulk_download_historical(
        self,
        tokens: List[str],
        days: int = 30,
        quote: str = "USD"
    ) -> pd.DataFrame:
        """
        Convenience method: Download N days of historical data for multiple tokens.

        This is the KEY method for initial historical backfill.
        """
        end_time = int(time.time())
        start_time = end_time - (days * 24 * 3600)

        all_data = []

        for token in tokens:
            market = f"{token}-{quote}"

            try:
                df = await self.get_historical_funding_rates(
                    market=market,
                    start_time=start_time,
                    end_time=end_time,
                    limit=10000
                )

                if not df.empty:
                    all_data.append(df)
                    print(f"✅ Downloaded {len(df)} records for {market}")
                else:
                    print(f"⚠️  No data for {market}")

                # Rate limiting
                await asyncio.sleep(0.5)

            except Exception as e:
                print(f"❌ Failed to download {market}: {e}")

        combined = pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()
        return combined.sort_values('timestamp')
```

**Effort**: 2 hours

---

### **3. Lighter API Data Source** (Optional/Future)

**File**: `/Users/tdl321/quants-lab/core/data_sources/lighter_funding.py` (FUTURE)

**Purpose**: Same interface, connects to Lighter API

```python
class LighterFundingDataSource(BaseFundingDataSource):
    """Lighter DEX API client - implement when needed."""

    BASE_URL = "https://mainnet.zklighter.elliot.ai/api/v1"

    # Implement same interface as Extended
    # ... (similar structure)
```

**Effort**: 2 hours (when needed)

---

### **4. Refactor CoinGecko to Match Interface**

**File**: `/Users/tdl321/quants-lab/core/data_sources/coingecko_funding.py` (MINOR CHANGES)

**Changes Needed**:
1. Inherit from `BaseFundingDataSource`
2. Ensure method signatures match interface
3. No logic changes - already compatible!

```python
from core.data_sources.base_funding_source import BaseFundingDataSource

class CoinGeckoFundingDataSource(BaseFundingDataSource):
    # Existing code - no changes needed!
    # Already implements all required methods
    pass
```

**Effort**: 15 minutes

---

### **5. Update FundingRateCollector** (MINIMAL CHANGES)

**File**: `/Users/tdl321/quants-lab/core/data_sources/funding_rate_collector.py` (MINOR UPDATE)

**Changes Needed**: Accept any `BaseFundingDataSource` instead of hardcoded CoinGecko

```python
from core.data_sources.base_funding_source import BaseFundingDataSource

class FundingRateCollector:
    def __init__(
        self,
        data_source: BaseFundingDataSource,  # ← Changed from specific CoinGeckoFundingDataSource
        exchanges: Optional[List[str]] = None,
        tokens: Optional[List[str]] = None,
        storage_path: Optional[str] = None
    ):
        self.cg_source = data_source  # Keep same variable name for compatibility
        # Rest of code unchanged
```

**Effort**: 5 minutes

---

## 🚀 Implementation Phases

### **Phase 1: Create Modular Foundation** (1 hour)

1. ✅ Create `BaseFundingDataSource` abstract class (30 min)
2. ✅ Update `CoinGeckoFundingDataSource` to inherit from base (15 min)
3. ✅ Update `FundingRateCollector` to accept base class (5 min)
4. ✅ Test that existing CoinGecko collection still works (10 min)

**Deliverable**: Existing system works with new architecture

---

### **Phase 2: Add Extended Data Source** (2 hours)

1. ✅ Create `ExtendedFundingDataSource` class (1 hour)
2. ✅ Test fetching markets from Extended API (15 min)
3. ✅ Test fetching 1-day historical data for 1 token (15 min)
4. ✅ Implement `bulk_download_historical()` method (30 min)

**Deliverable**: Can download historical data from Extended

---

### **Phase 3: Historical Data Download** (30 min)

1. ✅ Create script to download 30-90 days of Extended data (15 min)
2. ✅ Run download for all 10 tokens (10 min)
3. ✅ Validate data quality and save to parquet (5 min)

**Deliverable**: 30-90 days of historical funding rate data

---

### **Phase 4: Unified Data Loading** (30 min)

**Option A**: Keep data sources separate in storage
```
/app/data/cache/funding/
├── raw/
│   ├── extended/
│   │   └── 2025-10-01_to_2025-11-04.parquet  # Historical bulk download
│   └── coingecko/
│       └── 2025-11-04.parquet                 # Ongoing snapshots
```

**Option B**: Merge into unified storage (RECOMMENDED)
```
/app/data/cache/funding/
├── raw/
│   └── 2025-10-*.parquet, 2025-11-*.parquet   # All sources combined
```

Update `FundingRateBacktestDataProvider`:
- Already works! No changes needed if using Option B
- Just loads all parquet files regardless of source

**Effort**: 30 minutes

---

## 📊 Usage Examples

### **Example 1: Download Historical Data from Extended**

```python
from core.data_sources.extended_funding import ExtendedFundingDataSource

# Initialize Extended source
extended = ExtendedFundingDataSource()
await extended.start()

# Download 90 days for all tokens
tokens = ["KAITO", "IP", "GRASS", "ZEC", "APT", "SUI", "TRUMP", "LDO", "OP", "SEI"]

historical_df = await extended.bulk_download_historical(
    tokens=tokens,
    days=90,
    quote="USD"
)

# Save to parquet (merge with existing data)
from core.data_sources.funding_rate_collector import FundingRateCollector

collector = FundingRateCollector(data_source=extended)
collector.save_snapshot(historical_df, append=True)

await extended.stop()
```

---

### **Example 2: Continue Using CoinGecko for Ongoing Collection**

```python
from core.data_sources.coingecko_funding import CoinGeckoFundingDataSource
from core.data_sources.funding_rate_collector import FundingRateCollector

# CoinGecko for ongoing collection (aggregates both exchanges)
coingecko = CoinGeckoFundingDataSource(api_key="...")

collector = FundingRateCollector(
    data_source=coingecko,  # Plug in any data source!
    exchanges=["lighter", "extended"],
    tokens=["KAITO", "IP", "GRASS"]
)

# Collect hourly snapshots
await collector.start_collection(
    duration_hours=24 * 30,  # 30 days
    interval_minutes=60
)
```

---

### **Example 3: Use Extended for Ongoing Collection Instead**

```python
from core.data_sources.extended_funding import ExtendedFundingDataSource
from core.data_sources.funding_rate_collector import FundingRateCollector

# Extended for ongoing collection (direct from source)
extended = ExtendedFundingDataSource()

collector = FundingRateCollector(
    data_source=extended,  # Just swap the source!
    exchanges=["extended"],  # Only Extended
    tokens=["KAITO", "IP", "GRASS"]
)

await collector.start_collection(...)
```

---

### **Example 4: Backtest with Any Data Source**

```python
from core.backtesting.funding_rate_data_provider import FundingRateBacktestDataProvider

# Backtest provider doesn't care about data source!
# It just loads parquet files
provider = FundingRateBacktestDataProvider()
provider.load_data(start_date="2025-10-01", end_date="2025-11-04")

# Run backtest
rate = provider.get_funding_rate(timestamp, "extended", "KAITO")
spread = provider.get_spread(timestamp, "lighter", "extended", "KAITO")
```

**NO CHANGES NEEDED** - already works!

---

## 📁 File Structure

```
/Users/tdl321/quants-lab/
├── core/
│   ├── data_sources/
│   │   ├── base_funding_source.py          ← NEW (abstract interface)
│   │   ├── coingecko_funding.py            ← MINOR UPDATE (inherit from base)
│   │   ├── extended_funding.py             ← NEW (Extended API client)
│   │   ├── lighter_funding.py              ← FUTURE (Lighter API client)
│   │   └── funding_rate_collector.py       ← MINOR UPDATE (accept base class)
│   │
│   └── backtesting/
│       └── funding_rate_data_provider.py   ← NO CHANGES
│
├── scripts/
│   ├── download_extended_historical.py     ← NEW (bulk download script)
│   └── final_collection_test.py            ← EXISTS
│
└── app/data/cache/funding/
    └── raw/
        ├── 2025-10-*.parquet               ← Extended historical data
        └── 2025-11-*.parquet               ← CoinGecko + Extended combined
```

---

## ✅ Implementation Checklist

### **Phase 1: Modular Foundation** (1 hour)
- [ ] Create `base_funding_source.py` with abstract interface
- [ ] Update `coingecko_funding.py` to inherit from base
- [ ] Update `funding_rate_collector.py` to accept base class
- [ ] Test existing CoinGecko collection still works

### **Phase 2: Extended Data Source** (2 hours)
- [ ] Create `extended_funding.py` class
- [ ] Implement `get_available_markets()` method
- [ ] Implement `get_historical_funding_rates()` method
- [ ] Implement `bulk_download_historical()` method
- [ ] Test downloading 7 days for 1 token

### **Phase 3: Bulk Historical Download** (30 min)
- [ ] Create `download_extended_historical.py` script
- [ ] Map our token symbols to Extended market IDs
- [ ] Download 30-90 days for all 10 tokens
- [ ] Validate data quality
- [ ] Save to parquet storage

### **Phase 4: Validation** (30 min)
- [ ] Load Extended historical data in BacktestDataProvider
- [ ] Verify time range and data completeness
- [ ] Test spread calculations
- [ ] Run sample backtest with 30+ days of data

---

## 🎯 Success Criteria

After implementation:

✅ **Can download 30-90 days of Extended historical data** in 30 minutes
✅ **Existing CoinGecko collection continues to work** unchanged
✅ **Can easily swap data sources** by changing one parameter
✅ **No code duplication** - shared logic in base class
✅ **Ready to add Lighter API** in future (just copy Extended structure)
✅ **BacktestDataProvider works** with any data source
✅ **Can run meaningful backtests** with 30+ days of data

---

## 📊 Timeline

| Phase | Duration | Output |
|-------|----------|--------|
| 1. Modular Foundation | 1 hour | Working base architecture |
| 2. Extended API Client | 2 hours | Extended data source class |
| 3. Historical Download | 30 min | 30-90 days of data |
| 4. Validation & Testing | 30 min | Verified backtest-ready data |
| **TOTAL** | **4 hours** | **Ready to backtest** |

---

## 💡 Key Benefits

1. **Immediate**: Get 30-90 days of data in 4 hours (vs waiting 30 days)
2. **Modular**: Easy to add Lighter or other sources later
3. **Reusable**: 90% of existing code unchanged
4. **Flexible**: Can use CoinGecko, Extended, or both
5. **Scalable**: Adding new sources = create one new class

---

## 🔄 Next Steps

**Immediate**:
1. Create base interface
2. Build Extended API client
3. Download historical data
4. Run first backtest!

**Future** (when needed):
1. Add Lighter API client (same pattern)
2. Add other DEX APIs (Hyperliquid, Drift, etc.)
3. Implement real-time WebSocket feeds
4. Add data reconciliation between sources

