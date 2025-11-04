# CoinGecko API - Historical Funding Rate Analysis

**Date**: 2025-11-04
**Question**: Can we get historical funding rate data from CoinGecko API?

---

## ❌ Answer: NO - Historical Funding Rates Not Available

CoinGecko API **does NOT provide historical funding rate data** through any public or documented endpoint.

---

## 📊 Available Derivatives Endpoints

CoinGecko API offers **4 derivatives endpoints**, all providing **current/real-time data only**:

### 1. `/derivatives`
**Purpose**: Query all tickers from derivatives exchanges
**Returns**: Current funding rates, prices, open interest, volume

### 2. `/derivatives/exchanges`
**Purpose**: List all derivatives exchanges
**Returns**: Exchange metadata (ID, name, open interest aggregates)

### 3. `/derivatives/exchanges/{id}`
**Purpose**: Get specific exchange data
**Returns**: Exchange info with current tickers (including current funding_rate)
**Parameters**:
- `id` (required) - Exchange ID
- `include_tickers` (optional) - "all" or "unexpired"

### 4. `/derivatives/exchanges/list`
**Purpose**: Get exchange ID mappings
**Returns**: Simple list of exchange IDs and names

---

## 🔍 What We Verified

### ✅ Available:
- Current/real-time funding rates
- Current open interest
- Current volume
- Current prices for derivatives

### ❌ NOT Available:
- Historical funding rates
- Time-series funding rate data
- Historical derivatives data
- Any time/date parameters on derivatives endpoints

---

## 📈 Historical Data in CoinGecko API

CoinGecko **does** provide historical data for:
- ✅ Spot prices (via `/coins/{id}/market_chart`)
- ✅ Market cap
- ✅ Trading volume
- ✅ OHLCV data
- ✅ 10+ years of historical spot market data

But **NOT** for:
- ❌ Funding rates
- ❌ Derivatives-specific metrics over time

---

## 💡 Implications for Our Project

### Current Strategy: ✅ CORRECT
Our current implementation is the **only viable approach**:

1. **Poll current funding rates regularly** (hourly/minutely)
2. **Store snapshots locally** (parquet files)
3. **Build historical dataset over time**

### Why We Can't Use Historical API:
- No such endpoint exists
- Must collect data going forward
- Cannot backfill past data from CoinGecko

---

## 🎯 Recommendations

### Option 1: Continue Current Approach (RECOMMENDED)
**What**: Keep our polling-based collection system
**Pros**:
- Already implemented and working
- Only viable CoinGecko solution
- Full control over data quality
- No dependencies on external historical data

**Cons**:
- Need to wait to collect historical data
- Can't backtest on data from before collection started

**Timeline**:
- 7 days collection = 168 hourly snapshots
- 30 days collection = 720 hourly snapshots
- 90 days collection = 2160 hourly snapshots

### Option 2: Find Alternative Data Source
**Options**:
- Direct DEX APIs (Lighter, Extended) - May not have historical data either
- Paid derivatives data providers (Kaiko, Glassnode, etc.)
- On-chain indexers (The Graph, etc.)

**Evaluation Needed**:
- Do Lighter/Extended provide historical funding rate APIs?
- Cost of alternative data sources?
- Data quality and reliability?

### Option 3: Accelerated Collection + Paper Trading
**What**:
1. Start collecting data now (hourly)
2. Use first 7 days to validate strategy parameters
3. Run paper trading in parallel
4. Collect 30+ days before full backtesting

**Pros**:
- Start learning about the strategy immediately
- Validate in real-time
- Build confidence before backtesting

---

## 📝 What This Means for Implementation

### Components Status:

✅ **Component 1 (API Client)**: Complete - Correctly fetches current data
✅ **Component 2 (Data Collector)**: Complete - Stores snapshots over time
✅ **Component 3 (Backtest Provider)**: Complete - Loads historical snapshots

⏸️ **Component 4 (Strategy Adapter)**: Can proceed, but...
⚠️ **Limited Data**: Only 17 records (~11 minutes of data) currently

### To Run Meaningful Backtests:
**Minimum**: 7 days of data (168 snapshots)
**Recommended**: 30 days of data (720 snapshots)
**Ideal**: 90 days of data (2160 snapshots)

---

## 🚀 Action Items

### Immediate (Now):
1. ✅ Keep current implementation as-is (it's correct!)
2. ⏭️ **Decision Point**: Start long-term data collection OR find alternative data source

### Option A: Start Collection Now
```python
# Run this for 30 days
collector = FundingRateCollector(...)
await collector.start_collection(
    duration_hours=30 * 24,  # 30 days
    interval_minutes=60       # Hourly
)
```

**Timeline**:
- Start: Now
- Have 7-day dataset: Nov 11
- Have 30-day dataset: Dec 4

### Option B: Research Alternative APIs
- [ ] Check Lighter DEX API documentation
- [ ] Check Extended DEX API documentation
- [ ] Research paid derivatives data providers
- [ ] Estimate costs vs. value

### Option C: Hybrid Approach
- Start collecting now (Option A)
- While collecting, research alternatives (Option B)
- If find better source, switch; otherwise use collected data

---

## 🎲 Recommendation: **Option C (Hybrid)**

**Start collecting data immediately** with our working system, while simultaneously investigating if Lighter or Extended DEXs have their own historical funding rate APIs.

**Reasoning**:
1. **Time is valuable** - Every hour we wait is historical data lost
2. **Low cost** - Collection is automated and free (Demo API)
3. **Hedge our bets** - If alternatives don't exist, we're already collecting
4. **Can combine** - Can merge CoinGecko data with DEX API data later if available

**Next Step**: Shall I help you either:
- A) Set up long-term data collection (30-day run)
- B) Research Lighter/Extended DEX APIs for historical data
- C) Both (start collection + research in parallel)

---

## 📊 Data Collection Calculator

| Collection Period | Snapshots | Storage | Ready For Backtest? |
|------------------|-----------|---------|---------------------|
| 1 day (hourly)   | 24        | ~100 KB | ❌ Too little |
| 7 days (hourly)  | 168       | ~1 MB   | ⚠️ Minimum |
| 30 days (hourly) | 720       | ~5 MB   | ✅ Good |
| 90 days (hourly) | 2160      | ~15 MB  | ✅ Excellent |

Current collection: **17 records** (11 minutes) = **Insufficient**

