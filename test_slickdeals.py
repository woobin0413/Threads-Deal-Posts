"""Test Slickdeals scraping"""
import asyncio
from main import DealsFetcher, TextExtractor

async def test():
    async with DealsFetcher() as fetcher:
        deals = await fetcher.fetch_slickdeals_amazon(min_thumbs_up=30, max_deals=50)
        print(f'\n=== Found {len(deals)} Amazon deals from Slickdeals ===\n')

        for i, deal in enumerate(deals[:10], 1):
            print(f'{i}. {deal.title[:70]}')
            print(f'   👍 Thumbs up: {deal.score}')
            print(f'   💰 Price: ${deal.price}')
            if deal.discount_percentage:
                print(f'   🔥 Discount: {deal.discount_percentage}')
            print(f'   🔗 Slickdeals: {deal.link[:80]}...')

            # Try to extract ASIN if it's in the link
            asin = TextExtractor.extract_asin_from_url(deal.link)
            if asin:
                print(f'   ✅ ASIN: {asin}')
                affiliate_link = TextExtractor.create_affiliate_link(asin)
                print(f'   🎯 Affiliate: {affiliate_link}')
            else:
                print(f'   ❌ No ASIN found (might be category/promotion page)')
            print()

asyncio.run(test())
