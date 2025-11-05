"""
Automated Deals Fetcher and Threads Poster
This script fetches deals from free APIs and web scraping, then posts to Threads.
Designed to be run via Windows Task Scheduler or cron job.
"""

import os
import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass
import re
import time
import certifi
import aiohttp
from bs4 import BeautifulSoup
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('deals_poster.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class Deal:
    """Represents a single deal"""
    title: str
    price: str
    original_price: Optional[str]
    discount_percentage: Optional[str]
    store: str
    link: str
    image_url: Optional[str]
    description: Optional[str]
    score: int = 0  # Deal quality score for sorting


class DealsFetcher:
    """
    Fetches deals from various sources using both free APIs and web scraping.

    aiohttp is used for asynchronous HTTP requests, allowing multiple sources
    to be fetched concurrently, which is much faster than sequential requests.
    This is especially important when aggregating data from multiple sources.
    """

    def __init__(self):
        self.session = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

    async def __aenter__(self):
        """Create an aiohttp session for async HTTP requests"""
        self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()

    async def fetch_cheapshark_deals(self) -> List[Deal]:
        """
        Fetch gaming deals from CheapShark API - FREE, NO AUTH REQUIRED!
        CheapShark provides PC game deals from Steam, GOG, Epic Games, etc.
        API Documentation: https://apidocs.cheapshark.com/
        """
        deals = []
        try:
            # Get top deals sorted by deal rating
            url = "https://www.cheapshark.com/api/1.0/deals"
            params = {
                'pageSize': 10,
                'sortBy': 'DealRating',  # Best deals first
                'onSale': 1
            }

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    for item in data[:10]:  # Top 10 deals
                        try:
                            # Calculate discount percentage
                            normal_price = float(item.get('normalPrice', 0))
                            sale_price = float(item.get('salePrice', 0))
                            discount = 0
                            if normal_price > 0:
                                discount = int((1 - sale_price/normal_price) * 100)

                            deal = Deal(
                                title=f"{item.get('title', 'Unknown Game')} (PC Game)",
                                price=f"${item.get('salePrice', 'N/A')}",
                                original_price=f"${item.get('normalPrice', 'N/A')}",
                                discount_percentage=f"{discount}%" if discount > 0 else None,
                                store=item.get('storeName', 'PC Store'),
                                link=f"https://www.cheapshark.com/redirect?dealID={item.get('dealID', '')}",
                                image_url=item.get('thumb'),
                                description=f"Metacritic: {item.get('metacriticScore', 'N/A')}/100",
                                score=int(float(item.get('dealRating', 0)) * 10)  # Convert to score
                            )
                            deals.append(deal)
                        except Exception as e:
                            logger.error(f"Error parsing CheapShark item: {e}")
                            continue

        except Exception as e:
            logger.error(f"Error fetching from CheapShark API: {e}")

        logger.info(f"Fetched {len(deals)} deals from CheapShark")
        return deals

    async def fetch_dummy_api_deals(self) -> List[Deal]:
        """
        Fetch sample product deals from DummyJSON API - FREE, NO AUTH!
        This is a fake data API but useful for testing.
        API Documentation: https://dummyjson.com/docs/products
        """
        deals = []
        try:
            url = "https://dummyjson.com/products"
            params = {
                'limit': 10,
                'sortBy': 'discountPercentage',
                'order': 'desc'
            }

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    products = data.get('products', [])

                    for item in products[:10]:
                        try:
                            # Calculate sale price
                            price = float(item.get('price', 0))
                            discount = float(item.get('discountPercentage', 0))
                            sale_price = price * (1 - discount/100)

                            deal = Deal(
                                title=item.get('title', 'Unknown Product'),
                                price=f"${sale_price:.2f}",
                                original_price=f"${price:.2f}",
                                discount_percentage=f"{discount:.0f}%",
                                store=item.get('brand', 'Online Store'),
                                link="https://example.com",  # Dummy link
                                image_url=item.get('thumbnail'),
                                description=item.get('description', '')[:100],
                                score=int(item.get('rating', 0) * 20)  # Convert rating to score
                            )
                            deals.append(deal)
                        except Exception as e:
                            logger.error(f"Error parsing DummyJSON item: {e}")
                            continue

        except Exception as e:
            logger.error(f"Error fetching from DummyJSON API: {e}")

        logger.info(f"Fetched {len(deals)} sample deals from DummyJSON")
        return deals

    async def fetch_slickdeals(self) -> List[Deal]:
        """
        Fetch deals from Slickdeals using web scraping.
        BeautifulSoup is used to parse HTML content from websites.
        """
        deals = []
        try:
            url = "https://slickdeals.net/deals/"
            async with self.session.get(url) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    #print(soup.prettify()[:1000])  # Print first 1000 chars of prettified HTML for debugging
                    # Parse Slickdeals frontpage deals
                    deal_elements = soup.find_all('div', class_='fpItem', limit=10)

                    for elem in deal_elements:
                        try:
                            title_elem = elem.find('a', class_='itemTitle')
                            if not title_elem:
                                continue

                            title = title_elem.text.strip()
                            link = title_elem.get('href', '')
                            if not link.startswith('http'):
                                link = f"https://slickdeals.net{link}"

                            price_elem = elem.find('div', class_='itemPrice')
                            price = price_elem.text.strip() if price_elem else "See Deal"

                            store_elem = elem.find('span', class_='itemStore')
                            store = store_elem.text.strip() if store_elem else "Various"

                            # Try to extract deal score/rating
                            score_elem = elem.find('div', class_='itemRating')
                            score = 0
                            if score_elem:
                                try:
                                    score = int(re.search(r'\d+', score_elem.text).group())
                                except:
                                    pass

                            deal = Deal(
                                title=title[:100],  # Limit title length
                                price=price,
                                original_price=None,
                                discount_percentage=None,
                                store=store,
                                link=link,
                                image_url=None,
                                description=None,
                                score=score
                            )
                            deals.append(deal)
                        except Exception as e:
                            logger.error(f"Error parsing Slickdeals item: {e}")
                            continue

        except Exception as e:
            logger.error(f"Error fetching from Slickdeals: {e}")

        logger.info(f"Fetched {len(deals)} deals from Slickdeals")
        return deals

    async def fetch_reddit_deals(self) -> List[Deal]:
        """
        Fetch deals from Reddit r/deals using their JSON API.
        Reddit provides a JSON endpoint that doesn't require authentication.
        """
        deals = []
        try:
            url = "https://www.reddit.com/r/deals/hot.json"
            headers = {**self.headers, 'User-Agent': 'DealsBot/1.0'}

            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    posts = data.get('data', {}).get('children', [])

                    for post in posts[:10]:
                        post_data = post.get('data', {})
                        title = post_data.get('title', '')
                        url = post_data.get('url', '')

                        # Extract price from title if present
                        price_match = re.search(r'\$[\d,]+\.?\d*', title)
                        price = price_match.group() if price_match else "See Deal"

                        # Extract store from domain
                        store = "Various"
                        if url:
                            domain_match = re.search(r'https?://(?:www\.)?([^/]+)', url)
                            if domain_match:
                                store = domain_match.group(1).split('.')[0].capitalize()

                        deal = Deal(
                            title=title[:100],
                            price=price,
                            original_price=None,
                            discount_percentage=None,
                            store=store,
                            link=url,
                            image_url=None,
                            description=None,
                            score=post_data.get('score', 0)
                        )
                        deals.append(deal)

        except Exception as e:
            logger.error(f"Error fetching from Reddit: {e}")

        logger.info(f"Fetched {len(deals)} deals from Reddit")
        return deals

    async def fetch_all_deals(self) -> List[Deal]:
        """Fetch deals from all sources - both APIs and web scraping"""
        logger.info("Fetching deals from all sources...")

        # Fetch from all sources concurrently
        # Mix of free APIs and web scraping for diversity
        tasks = [
           # self.fetch_cheapshark_deals(),  # Free gaming deals API
           # self.fetch_slickdeals(),        # Web scraping popular deals
            self.fetch_reddit_deals(),       # Web scraping Reddit deals
        ]

        # Only add dummy API for testing if enabled
        if os.getenv('USE_DUMMY_DATA', 'false').lower() == 'true':
            tasks.append(self.fetch_dummy_api_deals())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_deals = []
        for result in results:
            if isinstance(result, list):
                all_deals.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Error in fetching task: {result}")

        # Sort by score and remove duplicates
        seen_titles = set()
        unique_deals = []
        for deal in sorted(all_deals, key=lambda x: x.score, reverse=True):
            # Simple duplicate check based on title similarity
            title_key = re.sub(r'[^a-zA-Z0-9]', '', deal.title.lower())[:50]
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_deals.append(deal)

        logger.info(f"Fetched {len(unique_deals)} unique deals")
        return unique_deals


class ThreadsAPI:
    """Handles posting to Threads using the official API"""

    def __init__(self):
        self.access_token = os.getenv('THREADS_ACCESS_TOKEN')
        self.user_id = os.getenv('THREADS_USER_ID')
        self.api_base = "https://graph.threads.net/v1.0"

        if not self.access_token or not self.user_id:
            raise ValueError("THREADS_ACCESS_TOKEN and THREADS_USER_ID must be set in .env file")

    def create_media_container(self, text: str, media_url: Optional[str] = None) -> Optional[str]:
        """Create a media container for a Threads post"""
        try:
            endpoint = f"{self.api_base}/{self.user_id}/threads"

            params = {
                'media_type': 'TEXT',
                'text': text,
                'access_token': self.access_token
            }

            if media_url:
                params['media_type'] = 'IMAGE'
                params['image_url'] = media_url

            response = requests.post(endpoint, params=params)
            response.raise_for_status()

            data = response.json()
            container_id = data.get('id')

            if container_id:
                logger.info(f"Created media container: {container_id}")
                return container_id
            else:
                logger.error(f"No container ID in response: {data}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating media container: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return None

    def publish_container(self, container_id: str) -> bool:
        """Publish a media container as a Threads post"""
        try:
            endpoint = f"{self.api_base}/{self.user_id}/threads_publish"

            params = {
                'creation_id': container_id,
                'access_token': self.access_token
            }

            response = requests.post(endpoint, params=params)
            response.raise_for_status()

            data = response.json()
            post_id = data.get('id')

            if post_id:
                logger.info(f"Published post: {post_id}")
                return True
            else:
                logger.error(f"No post ID in response: {data}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Error publishing container: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return False

    def post_to_threads(self, text: str) -> bool:
        """Create and publish a post to Threads"""
        container_id = self.create_media_container(text)
        if container_id:
            # Wait a moment between container creation and publishing
            time.sleep(1)
            return self.publish_container(container_id)
        return False

    def check_rate_limits(self) -> Dict:
        """Check current API rate limits"""
        try:
            endpoint = f"{self.api_base}/{self.user_id}/threads_publishing_limit"
            params = {
                'fields': 'quota_usage,config',
                'access_token': self.access_token
            }

            response = requests.get(endpoint, params=params)
            response.raise_for_status()

            data = response.json()
            logger.info(f"Rate limit status: {data}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking rate limits: {e}")
            return {}


class DealsPostManager:
    """Manages the process of fetching deals and posting to Threads"""

    def __init__(self):
        self.threads_api = ThreadsAPI()
        self.posted_deals_file = 'posted_deals.json'
        self.posted_deals = self.load_posted_deals()

    def load_posted_deals(self) -> List[str]:
        """Load previously posted deals to avoid duplicates"""
        if os.path.exists(self.posted_deals_file):
            try:
                with open(self.posted_deals_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []

    def save_posted_deals(self):
        """Save posted deals to file"""
        # Keep only last 100 deals to prevent file from growing too large
        self.posted_deals = self.posted_deals[-100:]
        with open(self.posted_deals_file, 'w') as f:
            json.dump(self.posted_deals, f)

    def format_deal_text(self, deal: Deal, index: int) -> str:
        """Format a single deal for posting"""
        emoji_map = {
            1: "🥇",
            2: "🥈",
            3: "🥉",
            4: "4️⃣",
            5: "5️⃣"
        }

        emoji = emoji_map.get(index, f"{index}.")

        # Format the deal text
        text = f"{emoji} {deal.title}\n"
        text += f"💰 {deal.price}"

        if deal.discount_percentage:
            text += f" ({deal.discount_percentage} OFF)"

        text += f"\n🏪 {deal.store}\n"

        # Shorten URL if possible (you might want to use a URL shortener API here)
        text += f"🔗 {deal.link}\n"

        return text

    def create_post_content(self, deals: List[Deal]) -> str:
        """Create the full post content from a list of deals"""
        header = "🔥 TODAY'S HOTTEST DEALS 🔥\n"
        header += f"📅 {datetime.now().strftime('%B %d, %Y')}\n"
        header += "─" * 30 + "\n\n"

        content = header

        for i, deal in enumerate(deals[:5], 1):  # Top 5 deals
            content += self.format_deal_text(deal, i)
            if i < 5:
                content += "\n"

        footer = "\n─" * 30 + "\n"
        footer += "💡 Follow for daily deals!\n"
        footer += "#deals #savings #shopping #discounts"

        content += footer

        # Threads has a 500 character limit
        if len(content) > 500:
            # Truncate smartly
            content = content[:497] + "..."

        return content

    async def fetch_and_post_deals(self):
        """Main function to fetch deals and post to Threads"""
        logger.info("Starting deals fetch and post process...")

        # Check rate limits first
        rate_limits = self.threads_api.check_rate_limits()

        # Fetch deals
        async with DealsFetcher() as fetcher:
            deals = await fetcher.fetch_all_deals()

        if not deals:
            logger.warning("No deals fetched")
            return

        # Filter out previously posted deals
        new_deals = []
        for deal in deals:
            deal_id = f"{deal.store}_{deal.title[:50]}"
            if deal_id not in self.posted_deals:
                new_deals.append(deal)
                self.posted_deals.append(deal_id)

        if not new_deals:
            logger.info("No new deals to post")
            return

        # Select top 5 deals
        top_deals = new_deals[:5]

        # Create and post content
        post_content = self.create_post_content(top_deals)
        logger.info(f"Post content ({len(post_content)} chars):\n{post_content}")

        # Post to Threads
        success = self.threads_api.post_to_threads(post_content)

        if success:
            logger.info("Successfully posted deals to Threads!")
            self.save_posted_deals()
        else:
            logger.error("Failed to post deals to Threads")


def main():
    """
    Main entry point - runs once when executed.
    Schedule this script using Windows Task Scheduler or cron to run twice daily.
    """
    logger.info("="*50)
    logger.info("Starting Deals to Threads poster...")
    logger.info(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*50)
    #
    # async def test_redditDeals():
    #     async with DealsFetcher() as fetcher:
    #         deals = await fetcher.fetch_reddit_deals()
    #         for deal in deals:
    #             print(deal)
    #
    # try:
    #     asyncio.run(test_redditDeals())
    #     logger.info("Slickdeals fetch test completed successfully!")
    #     return 0  # Success
    # #
    # # Check for required environment variables
    required_env = ['THREADS_ACCESS_TOKEN', 'THREADS_USER_ID']
    missing = [var for var in required_env if not os.getenv(var)]


    if missing:
        logger.error(f"Missing required environment variables: {missing}")
        logger.error("Please set them in your .env file")
        return 1  # Return error code for scheduler

    try:
        # Create manager and run the posting process
        manager = DealsPostManager()
        asyncio.run(manager.fetch_and_post_deals())

        logger.info("="*50)
        logger.info("Successfully completed deals posting!")
        logger.info("="*50)
        return 0  # Success

    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1  # Return error code


if __name__ == "__main__":
    exit(main())