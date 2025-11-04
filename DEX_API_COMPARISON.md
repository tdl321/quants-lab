# DEX API Comparison: Funding Rate Data Access

**Date**: 2025-11-04
**Question**: Should we use Lighter/Extended APIs instead of CoinGecko?

---

## 🎯 Summary: YES - Extended Has Historical Funding Rates!

**Extended DEX** provides a **historical funding rate API** that would be far superior to polling CoinGecko.

---

## 📊 API Comparison

### **Extended DEX API** ✅ WINNER

**Historical Funding Rate Endpoint**:
```
GET /api/v1/info/{market}/funding?startTime={startTime}&endTime={endTime}
```

**Features**:
- ✅ **Historical data available** with time range parameters
- ✅ `startTime` and `endTime` parameters (query by date range)
- ✅ Returns up to 10,000 records per request
- ✅ Sorted by timestamp (descending order)
- ✅ Funding rates calculated every minute, applied hourly
- ✅ Pagination support with `cursor` parameter
- ✅ Market-specific queries

**Response Format**:
```json
{
  "m": "BTC-USD",      // Market
  "T": 1234567890,      // Timestamp
  "f": 0.0001           // Funding rate
}
```

**Additional Endpoints**:
- `/api/v1/info/markets` - Get all markets
- `/api/v1/info/markets/{market}/stats` - Market statistics
- `/api/v1/info/candles/{market}/{candleType}` - Historical price data
- `/api/v1/info/{market}/open-interests` - Historical open interest

**Documentation**: https://api.docs.extended.exchange/

---

### **Lighter DEX API** ⚠️ UNCLEAR

**Funding Rate Endpoint**:
```
GET https://mainnet.zklighter.elliot.ai/api/v1/funding-rates
```

**Status**:
- ⚠️ Endpoint exists but parameters not fully documented
- ⚠️ Unclear if historical data available
- ⚠️ No visible `startTime`/`endTime` parameters in docs
- ✅ WebSocket channel includes funding rate updates
- ✅ Account-level funding history available

**Documentation**: https://apidocs.lighter.xyz/reference/funding-rates

**Note**: May require API testing to determine full capabilities

---

### **CoinGecko API** ❌ NO HISTORICAL DATA

**Endpoint**:
```
GET /api/v3/derivatives/exchanges/{id}?include_tickers=unexpired
```

**Limitations**:
- ❌ **No historical data**
- ❌ Only current/real-time funding rates
- ❌ No time parameters
- ❌ Must poll and store yourself

---

## 💡 Recommendation: Use Extended API for Historical Data

### **NEW PROPOSED ARCHITECTURE**

```
┌─────────────────────────────────────────┐
│  Extended API (Historical Backfill)      │
│  /api/v1/info/{market}/funding           │
│  • Get last 30-90 days of data           │
│  • One-time bulk download                │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│  Local Storage (Parquet Files)           │
│  • Historical data from Extended         │
│  • Ongoing snapshots from CoinGecko      │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│  FundingRateBacktestDataProvider         │
│  • Unified interface                      │
│  • Loads from any source                  │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│  Backtesting Engine                       │
└─────────────────────────────────────────┘
```

---

## 🚀 Implementation Strategy

### **Phase 1: Backfill Historical Data (NEW)**

**Create Extended API Client** to fetch historical funding rates:

```python
class ExtendedFundingDataSource:
    BASE_URL = "https://api.extended.exchange"

    async def get_historical_funding_rates(
        self,
        market: str,          # e.g., "BTC-USD"
        start_time: int,      # Unix timestamp
        end_time: int,        # Unix timestamp
        limit: int = 10000
    ) -> pd.DataFrame:
        """Fetch historical funding rates from Extended."""
        url = f"{self.BASE_URL}/api/v1/info/{market}/funding"
        params = {
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }
        # ... fetch and parse
        return df
```

**Timeline**: 1-2 hours to implement

---

### **Phase 2: Bulk Download**

**Download 30-90 days of historical data** for all tokens:

```python
# For each token on Extended
tokens = ["KAITO", "IP", "GRASS", "ZEC", "APT", "SUI", "TRUMP", "LDO", "OP", "SEI"]

for token in tokens:
    market = f"{token}-USD"  # or {token}-USDC

    # Get last 90 days
    end_time = int(time.time())
    start_time = end_time - (90 * 24 * 3600)

    df = await extended_client.get_historical_funding_rates(
        market=market,
        start_time=start_time,
        end_time=end_time
    )

    # Save to parquet
    save_to_parquet(df, f"extended_{token}_historical.parquet")
```

**Timeline**: 10-20 minutes to download all tokens

---

### **Phase 3: Ongoing Updates**

**Options**:

**A) Switch to Extended API for ongoing collection**
- Pro: Direct source, likely more reliable
- Con: Need to implement Extended API client

**B) Keep CoinGecko for ongoing collection**
- Pro: Already implemented and working
- Con: Using different sources (Extended historical + CoinGecko current)

**C) Hybrid: Extended for backfill, CoinGecko for ongoing**
- Pro: Best of both worlds
- Pro: CoinGecko aggregates multiple exchanges
- Con: Potential data format differences

---

## 📋 Market Name Mapping

Need to map our token symbols to Extended market IDs:

| Token  | CoinGecko Symbol | Extended Market ID | Notes |
|--------|------------------|-------------------|-------|
| KAITO  | KAITO           | KAITO-USD ?       | Need to verify |
| IP     | IP              | IP-USD ?          | Need to verify |
| GRASS  | GRASS           | GRASS-USD ?       | Need to verify |
| ZEC    | ZEC             | ZEC-USD ?         | Need to verify |
| APT    | APT             | APT-USD ?         | Need to verify |
| SUI    | SUI             | SUI-USD ?         | Need to verify |
| TRUMP  | TRUMP           | TRUMP-USD ?       | Need to verify |
| LDO    | LDO             | LDO-USD ?         | Need to verify |
| OP     | OP              | OP-USD ?          | Need to verify |
| SEI    | SEI             | SEI-USD ?         | Need to verify |

**Action Required**: Query Extended `/api/v1/info/markets` to get all available markets

---

## 🔧 Implementation Effort

### **Option 1: Extended Only (Clean Slate)**
**Effort**: Medium (4-6 hours)
- New API client for Extended
- Bulk historical download
- Ongoing polling from Extended
- Market name mapping
- Data format standardization

**Benefits**:
- ✅ Single data source (consistent)
- ✅ 30-90 days of historical data immediately
- ✅ Can backtest right away

**Risks**:
- ⚠️ Only Extended data (no Lighter comparison)
- ⚠️ Need to handle Extended API changes

---

### **Option 2: Hybrid (Extended Historical + CoinGecko Ongoing)**
**Effort**: Low-Medium (2-3 hours)
- New API client for Extended (historical only)
- One-time bulk download
- Keep existing CoinGecko collector
- Merge data in BacktestDataProvider

**Benefits**:
- ✅ Minimal changes to existing system
- ✅ Historical data immediately
- ✅ CoinGecko aggregates both exchanges
- ✅ Redundancy (if one API fails, have the other)

**Risks**:
- ⚠️ Data format differences
- ⚠️ Need to handle timestamp alignment

---

### **Option 3: Dual Collection (Extended + Lighter)**
**Effort**: High (6-8 hours)
- Extended API client
- Lighter API client (if historical available)
- Fetch from both DEXs directly
- Data merging and deduplication
- Spread calculation across 4 sources

**Benefits**:
- ✅ Most comprehensive data
- ✅ Direct from source (no aggregator)
- ✅ Can validate CoinGecko accuracy

**Risks**:
- ⚠️ High complexity
- ⚠️ More API keys/auth to manage
- ⚠️ Likely overkill for initial backtesting

---

## 🎯 My Recommendation: **Option 2 (Hybrid)**

**Why**:
1. **Quick win**: Get 30-90 days of Extended historical data in 2-3 hours
2. **Low risk**: Keep existing CoinGecko system that works
3. **Immediate backtesting**: Can run meaningful backtests today
4. **Best ROI**: Minimal effort for maximum data coverage

**Implementation Steps**:
1. Create `ExtendedFundingDataSource` class (1 hour)
2. Query `/api/v1/info/markets` to map token names (15 min)
3. Bulk download 30 days of Extended historical data (30 min)
4. Update `FundingRateBacktestDataProvider` to load Extended data (30 min)
5. Test backtest with historical data (30 min)

**Total Time**: ~3 hours to have 30 days of backtest-ready data

---

## 📊 Data Availability Estimate

### **Extended Historical Data**
Assuming Extended has been live since early 2024:
- **Available**: Likely 3-12 months of historical funding rates
- **Request**: Get last 90 days (conservative)
- **Records**: ~2,160 per token (90 days × 24 hours)
- **Total**: ~21,600 records for 10 tokens

### **Storage**
- Extended historical: ~15-20 MB (90 days, 10 tokens)
- CoinGecko ongoing: ~5 MB per month
- Total: ~25 MB for comprehensive dataset

---

## ✅ Next Steps

### **Immediate (Do Now)**:
1. ✅ Test Extended API endpoint to verify it works
2. ✅ Get list of available markets from Extended
3. ✅ Verify which of our 10 tokens are on Extended
4. ✅ Test downloading 7 days of historical data for 1 token

### **After Validation**:
1. Build `ExtendedFundingDataSource` class
2. Download 30-90 days historical data
3. Update `FundingRateBacktestDataProvider` to load it
4. Run first meaningful backtest!

---

**Shall I proceed with testing the Extended API and building the historical data downloader?**

