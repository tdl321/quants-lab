"""Check Extended markets data for KAITO and funding rates."""

import asyncio
import aiohttp
import json


async def main():
    """Check markets."""
    url = "https://api.extended.exchange/api/v1/info/markets"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()

            markets = data.get('data', [])
            print(f"Total markets: {len(markets)}")

            # Find our target tokens
            target_tokens = ['KAITO', 'IP', 'GRASS', 'ZEC', 'APT', 'SUI', 'TRUMP', 'LDO', 'OP', 'SEI']

            print("\n" + "=" * 80)
            print("Target Tokens on Extended")
            print("=" * 80)

            found = []
            for market in markets:
                asset = market.get('assetName', '')
                if asset in target_tokens:
                    name = market.get('name', '')
                    status = market.get('status', '')
                    stats = market.get('marketStats', {})
                    funding_rate = stats.get('fundingRate', '0')

                    print(f"\n{asset} ({name}):")
                    print(f"  Status: {status}")
                    print(f"  Funding Rate: {funding_rate}")
                    print(f"  Index Price: {stats.get('indexPrice', 'N/A')}")
                    print(f"  Last Price: {stats.get('lastPrice', 'N/A')}")
                    print(f"  Volume: {stats.get('dailyVolume', 'N/A')}")

                    found.append(asset)

            print(f"\n\nFound {len(found)}/{len(target_tokens)} tokens: {found}")

            missing = [t for t in target_tokens if t not in found]
            if missing:
                print(f"Missing: {missing}")


if __name__ == "__main__":
    asyncio.run(main())
