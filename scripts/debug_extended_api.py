"""
Debug Extended API responses to understand the actual data format.
"""

import asyncio
import aiohttp
import json
from datetime import datetime


async def debug_markets_endpoint():
    """Debug the markets endpoint."""
    print("=" * 80)
    print("DEBUG: Markets Endpoint")
    print("=" * 80)

    url = "https://api.extended.exchange/api/v1/info/markets"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                print(f"Status: {response.status}")
                print(f"Headers: {dict(response.headers)}")
                print()

                data = await response.json()
                print(f"Response type: {type(data)}")
                print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
                print()
                print("Raw JSON response:")
                print(json.dumps(data, indent=2)[:2000])  # First 2000 chars

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()


async def debug_funding_endpoint():
    """Debug the funding rate endpoint."""
    print("\n" + "=" * 80)
    print("DEBUG: Funding Rate Endpoint")
    print("=" * 80)

    # Try different market formats
    test_markets = [
        "KAITO-USD",
        "KAITO-USDC",
        "KAITO",
        "kaito-usd",
    ]

    end_time = int(datetime.now().timestamp())
    start_time = end_time - (7 * 24 * 3600)  # 7 days ago

    async with aiohttp.ClientSession() as session:
        for market in test_markets:
            print(f"\nTesting market: {market}")
            url = f"https://api.extended.exchange/api/v1/info/{market}/funding"
            params = {
                "startTime": start_time,
                "endTime": end_time,
                "limit": 10
            }

            print(f"URL: {url}")
            print(f"Params: {params}")

            try:
                async with session.get(url, params=params) as response:
                    print(f"Status: {response.status}")

                    if response.status == 200:
                        data = await response.json()
                        print(f"Response type: {type(data)}")

                        if isinstance(data, list):
                            print(f"Response length: {len(data)}")
                            if len(data) > 0:
                                print("First item:")
                                print(json.dumps(data[0], indent=2))
                        elif isinstance(data, dict):
                            print(f"Response keys: {list(data.keys())}")
                            print("Response:")
                            print(json.dumps(data, indent=2)[:1000])
                        else:
                            print(f"Unexpected type: {data}")
                    else:
                        text = await response.text()
                        print(f"Error response: {text[:500]}")

            except Exception as e:
                print(f"Error: {e}")

            await asyncio.sleep(1)


async def main():
    """Run debug tests."""
    await debug_markets_endpoint()
    await debug_funding_endpoint()


if __name__ == "__main__":
    asyncio.run(main())
