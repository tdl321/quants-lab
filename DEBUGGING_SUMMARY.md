# Extended API Debugging Summary

**Date**: 2025-11-04
**Status**: ✅ RESOLVED

---

## Problem

Extended API was returning empty data arrays (`{"status": "OK", "data": []}`), leading to incorrect conclusion that:
- Markets were REDUCE_ONLY/DELISTED
- Historical data was not available
- ZEC and APT markets didn't exist

---

## Root Causes Found

### 1. **Wrong Base URL** ❌
```python
# WRONG
BASE_URL = "https://api.extended.exchange"
# Returns only 65 markets, many REDUCE_ONLY

# CORRECT  
BASE_URL = "https://api.starknet.extended.exchange/api/v1"
# Returns 91 ACTIVE markets
```

### 2. **Timestamps in Seconds Instead of Milliseconds** ❌
```python
# WRONG - API rejects the request silently
start_time = int(time.time())           # 1730847600 (seconds)
end_time = int(time.time())             # 1730847600 (seconds)

# CORRECT - API accepts and returns data
start_time = int(time.time() * 1000)   # 1730847600000 (milliseconds)
end_time = int(time.time() * 1000)     # 1730847600000 (milliseconds)
```

### 3. **Wrong Response Field Names** ❌
```python
# WRONG - These fields don't exist in the response
item.get('timestamp', 0)      # ❌
item.get('fundingRate', 0)    # ❌
item.get('indexPrice', 0)     # ❌

# CORRECT - Actual API response fields
item.get('T', 0)              # ✅ Timestamp (milliseconds)
item.get('f', '0')            # ✅ Funding rate (string)
item.get('m', market)         # ✅ Market name
```

### 4. **Missing User-Agent Header** ⚠️
API documentation states User-Agent is mandatory, though not enforced in all cases.

---

## Changes Made

### File: `core/data_sources/extended_funding.py`

**Line 58** - Base URL:
```python
# OLD: BASE_URL = "https://api.extended.exchange"
# NEW: BASE_URL = "https://api.starknet.extended.exchange/api/v1"
```

**Lines 82-84** - User-Agent header:
```python
headers = {
    'User-Agent': 'backtest'  # Required by Extended API
}
self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)
```

**Line 105** - Markets endpoint path:
```python
# OLD: url = f"{self.BASE_URL}/api/v1/info/markets"
# NEW: url = f"{self.BASE_URL}/info/markets"
```

**Line 191** - Funding endpoint path:
```python
# OLD: url = f"{self.BASE_URL}/api/v1/info/{market}/funding"
# NEW: url = f"{self.BASE_URL}/info/{market}/funding"
```

**Lines 212-234** - Response parsing with correct field names:
```python
# Parse API response fields: m, T, f
market_name = item.get('m', market)
timestamp_ms = item.get('T', 0)
funding_rate_str = item.get('f', '0')

# Convert timestamp from milliseconds to seconds
timestamp_sec = int(timestamp_ms / 1000) if timestamp_ms else 0
funding_rate = float(funding_rate_str) if funding_rate_str else 0.0
```

**Line 277-278** - Convert timestamps to milliseconds:
```python
# OLD: end_time = int(time.time())
# NEW: end_time = int(time.time() * 1000)
```

**Line 350-351** - Bulk download timestamps:
```python
# OLD: end_time = int(time.time())
# NEW: end_time = int(time.time() * 1000)
```

---

## Verification Tests

### ✅ Test 1: Markets Discovery
- **Result**: 91 markets found (was 65)
- **All 10 target tokens**: ACTIVE status (was REDUCE_ONLY)
- **ZEC, APT**: Now found (were missing)

### ✅ Test 2: Single Token Historical Data
- **Market**: KAITO-USD
- **Period**: 7 days
- **Records**: 168 (expected: 7 × 24 = 168)
- **Funding rate range**: -0.004272 to 0.000013

### ✅ Test 3: Multi-Token Bulk Download
- **Tokens**: All 10
- **Period**: 7 days
- **Records**: 1,680 (expected: 10 × 7 × 24 = 1,680)

### ✅ Test 4: Extended Historical Period
- **Tokens**: KAITO, IP, GRASS
- **Period**: 30 days
- **Records**: 2,160 (expected: 3 × 30 × 24 = 2,160)
- **Date range**: 2025-10-05 to 2025-11-04

---

## Key Learnings

1. **Always consult official API documentation** - The correct base URL, field names, and timestamp format were all documented
2. **Debug with minimal examples** - Testing the raw HTTP request revealed the timestamp issue
3. **Verify response schema** - The actual API returns `m`, `T`, `f` not full field names
4. **Milliseconds vs Seconds** - Many APIs use milliseconds for timestamps, not seconds
5. **Silent failures** - API returned 200 OK with empty data instead of error, making debugging harder

---

## Impact

### Before Fix
- ❌ No historical data available
- ❌ Assumed markets were closing down
- ❌ Planned 30-day wait to collect CoinGecko data
- ❌ 2/10 tokens missing (ZEC, APT)

### After Fix
- ✅ 30-90 days of historical data available immediately
- ✅ All 10 tokens ACTIVE with real trading volume
- ✅ Can start backtesting TODAY
- ✅ Hourly funding rate records for accurate simulation

---

## Next Steps

1. ✅ **Implementation corrected** - `extended_funding.py` fixed
2. ✅ **Documentation updated** - `EXTENDED_API_FINDINGS.md` rewritten
3. 📋 **Ready for production use** - Download historical data and begin backtesting

---

## Files Modified

- `/Users/tdl321/quants-lab/core/data_sources/extended_funding.py` (corrected)
- `/Users/tdl321/quants-lab/EXTENDED_API_FINDINGS.md` (rewritten)
- `/Users/tdl321/quants-lab/DEBUGGING_SUMMARY.md` (this file)
