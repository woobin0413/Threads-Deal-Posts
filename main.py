"""
Automated Deals Fetcher and Threads Poster
This script fetches deals from free APIs and web scraping, then posts to Threads.
Designed to be run via Windows Task Scheduler or cron job.
"""

import os
import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum

import aiohttp
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# Load environment variables - override system env vars with .env file
load_dotenv(override=True)

# ============= CONFIGURATION =============
class Config:
    """Application configuration constants"""
    # API Configuration
    THREADS_API_BASE = "https://graph.threads.net/v1.0"

    # Deal Configuration
    TOP_DEALS_COUNT = 4
    MAX_TITLE_LENGTH = 100
    MAX_POSTED_DEALS_HISTORY = 100
    DUPLICATE_TITLE_KEY_LENGTH = 50

    # Post Configuration
    MAX_POST_LENGTH = 2000  # Threads supports up to 500 chars per post, but we'll format nicely
    SEPARATOR_LINE = "─" * 30

    # File paths
    POSTED_DEALS_FILE = 'posted_deals.json'
    LOG_FILE = 'deals_poster.log'
    DEALS_LINKS_FILE = 'deals_links.txt'

    # HTTP Configuration
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    REDDIT_USER_AGENT = 'DealsBot/1.0'
    CONTAINER_PUBLISH_DELAY = 1  # seconds

    # Default values
    DEFAULT_PRICE = "See Deal"
    DEFAULT_STORE = "Various"

    # Emoji mapping
    RANK_EMOJIS = {1: "🥇", 2: "🥈", 3: "🥉", 4: "4️⃣"}


# ============= LOGGING SETUP =============
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============= DATA MODELS =============
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
    score: int = 0
    short_link: Optional[str] = None  # Shortened link (e.g., amzn.to)

    def get_unique_id(self) -> str:
        """Generate unique ID for duplicate detection"""
        return f"{self.store}_{self.title[:50]}"

    def get_normalized_title(self) -> str:
        """Get normalized title for duplicate detection"""
        return re.sub(r'[^a-zA-Z0-9]', '', self.title.lower())[:Config.DUPLICATE_TITLE_KEY_LENGTH]


# ============= UTILITY FUNCTIONS =============
class TextExtractor:
    """Utility class for extracting information from text"""

    @staticmethod
    def extract_price(text: str) -> str:
        """Extract price from text using regex"""
        price_match = re.search(r'\$[\d,]+\.?\d*', text)
        return price_match.group() if price_match else Config.DEFAULT_PRICE

    @staticmethod
    def extract_store_from_url(url: str) -> str:
        """Extract store name from URL domain"""
        if not url:
            return Config.DEFAULT_STORE
        domain_match = re.search(r'https?://(?:www\.)?([^/]+)', url)
        if domain_match:
            return domain_match.group(1).split('.')[0].capitalize()
        return Config.DEFAULT_STORE

    @staticmethod
    def extract_score_from_text(text: str) -> int:
        """Extract numeric score from text"""
        try:
            match = re.search(r'\d+', text)
            return int(match.group()) if match else 0
        except (AttributeError, ValueError):
            return 0


# ============= DEALS FETCHER =============
class DealsFetcher:
    """Fetches deals from various sources using async HTTP requests"""

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.headers = {'User-Agent': Config.USER_AGENT}

    async def __aenter__(self):
        """Create aiohttp session for async HTTP requests"""
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()

    async def _fetch_json(self, url: str, headers: Optional[Dict] = None) -> Optional[Dict]:
        """Generic method to fetch JSON from URL"""
        try:
            async with self.session.get(url, headers=headers or self.headers) as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            logger.error(f"Error fetching JSON from {url}: {e}")
        return None

    async def fetch_reddit_deals(self) -> List[Deal]:
        """Fetch deals from Reddit r/deals using JSON API"""
        deals = []
        url = "https://www.reddit.com/r/deals/hot.json"
        headers = {**self.headers, 'User-Agent': Config.REDDIT_USER_AGENT}

        data = await self._fetch_json(url, headers)
        if not data:
            return deals

        posts = data.get('data', {}).get('children', [])

        for idx, post in enumerate(posts[:10], 1):
            post_data = post.get('data', {})

            # Skip promoted posts
            if post_data.get('promoted') or post_data.get('is_sponsored'):
                logger.debug(f"Skipping promoted post: {post_data.get('title', '')}")
                continue

            title = post_data.get('title', '')
            url = post_data.get('url', '')

            # Extract image URL from Reddit post
            image_url = None
            # Try preview images first (high quality)
            preview = post_data.get('preview', {})
            if preview and 'images' in preview and len(preview['images']) > 0:
                image_url = preview['images'][0].get('source', {}).get('url', '')
                # Reddit escapes HTML entities in URLs, unescape them
                if image_url:
                    image_url = image_url.replace('&amp;', '&')
            # Fallback to thumbnail if no preview
            elif post_data.get('thumbnail') and post_data['thumbnail'].startswith('http'):
                image_url = post_data['thumbnail']

            deal = Deal(
                title=title[:Config.MAX_TITLE_LENGTH],
                price=TextExtractor.extract_price(title),
                original_price=None,
                discount_percentage=None,
                store=TextExtractor.extract_store_from_url(url),
                link=url,
                image_url=image_url,
                description=None,
                score=post_data.get('score', 0)
            )

            # Debug output
            logger.debug(f"Deal #{idx}: {deal.title} - ${deal.price} ({deal.score})")
            deals.append(deal)

        logger.info(f"Fetched {len(deals)} deals from Reddit")
        return deals

    def _remove_duplicates(self, deals: List[Deal]) -> List[Deal]:
        """Remove duplicate deals based on normalized titles"""
        seen_titles = set()
        unique_deals = []

        for deal in sorted(deals, key=lambda x: x.score, reverse=True):
            title_key = deal.get_normalized_title()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_deals.append(deal)

        return unique_deals

    async def fetch_amazon_from_links(self, links_file: str = Config.DEALS_LINKS_FILE) -> List[Deal]:
        """Fetch Amazon product details from shortened links in a text file"""
        deals = []

        # Read links from file
        if not os.path.exists(links_file):
            logger.warning(f"Links file not found: {links_file}")
            return deals

        with open(links_file, 'r') as f:
            links = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]

        logger.info(f"Fetching {len(links)} deals from Amazon links...")

        for idx, short_link in enumerate(links, 1):
            try:
                async with self.session.get(short_link, headers=self.headers, allow_redirects=True) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to fetch {short_link}: Status {response.status}")
                        continue

                    html = await response.text()
                    soup = BeautifulSoup(html, 'lxml')

                    # Extract product title
                    title_elem = soup.find('span', {'id': 'productTitle'})
                    title = title_elem.get_text(strip=True) if title_elem else f"Amazon Deal {idx}"

                    # Extract price
                    price_elem = soup.find('span', {'class': 'a-offscreen'})
                    price = price_elem.get_text(strip=True) if price_elem else "See Deal"

                    # Extract discount percentage
                    discount_elem = soup.find('span', {'class': 'savingsPercentage'})
                    discount = discount_elem.get_text(strip=True) if discount_elem else None

                    # Extract product image
                    img_elem = soup.find('img', {'id': 'landingImage'})
                    image_url = img_elem.get('src') if img_elem else None

                    # Extract product features/description (only first feature)
                    description = None
                    feature_bullets = soup.find('div', {'id': 'feature-bullets'})
                    if feature_bullets:
                        bullets = feature_bullets.find_all('span', {'class': 'a-list-item'})
                        for bullet in bullets[:1]:  # Get only first feature
                            text = bullet.get_text(strip=True)
                            if text and len(text) > 10:  # Skip empty or very short items
                                description = text
                                break

                    deal = Deal(
                        title=title[:Config.MAX_TITLE_LENGTH],
                        price=price.replace('$', ''),
                        original_price=None,
                        discount_percentage=discount,
                        store="Amazon",
                        link=str(response.url),  # Full URL after redirect
                        short_link=short_link,   # Keep the shortened link
                        image_url=image_url,
                        description=description,
                        score=100 - idx  # Higher score for earlier items in the list
                    )

                    deals.append(deal)
                    logger.info(f"Fetched: {title[:60]}... - {price}")

            except Exception as e:
                logger.error(f"Error fetching {short_link}: {e}")
                continue

        logger.info(f"Successfully fetched {len(deals)} deals from links")
        return deals

    async def fetch_all_deals(self) -> List[Deal]:
        """Fetch deals from links file or Reddit"""
        # Check if links file exists and has content
        if os.path.exists(Config.DEALS_LINKS_FILE):
            with open(Config.DEALS_LINKS_FILE, 'r') as f:
                links = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]

            if links:
                logger.info(f"Using deals from {Config.DEALS_LINKS_FILE}")
                deals = await self.fetch_amazon_from_links()
                return deals

        # Fallback to Reddit
        logger.info("Fetching deals from Reddit...")
        deals = await self.fetch_reddit_deals()
        unique_deals = self._remove_duplicates(deals)
        logger.info(f"Fetched {len(unique_deals)} unique deals")
        return unique_deals


# ============= THREADS API =============
class ThreadsAPI:
    """Handles posting to Threads using the official API"""

    def __init__(self):
        self.access_token = os.getenv('THREADS_ACCESS_TOKEN')
        self.user_id = os.getenv('THREADS_USER_ID')
        self.api_base = Config.THREADS_API_BASE

        if not self.access_token or not self.user_id:
            raise ValueError("THREADS_ACCESS_TOKEN and THREADS_USER_ID must be set")

    def _make_request(self, method: str, endpoint: str, params: Dict) -> Optional[Dict]:
        """Generic method to make API requests with error handling"""
        try:
            url = f"{self.api_base}/{endpoint}"
            request_func = requests.post if method == 'POST' else requests.get

            response = request_func(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request error ({method} {endpoint}): {e}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return None

    def create_media_container(self, text: str = "", media_url: Optional[str] = None, is_carousel_item: bool = False) -> Optional[str]:
        """Create a media container for a Threads post

        POST /{threads-user-id}/threads
        Required params: media_type, access_token
        Optional: text, image_url
        """
        params = {
            'media_type': 'IMAGE' if media_url else 'TEXT',
            'access_token': self.access_token
        }

        # Only add text for carousel container, not individual items
        if text and not is_carousel_item:
            params['text'] = text

        if media_url:
            params['image_url'] = media_url

        logger.info(f"Creating media container with params: media_type={params['media_type']}, text_length={len(text) if text else 0}")
        data = self._make_request('POST', f"{self.user_id}/threads", params)

        if data and 'id' in data:
            container_id = data['id']
            logger.info(f"Created media container (creation_id): {container_id}")
            return container_id

        logger.error(f"No container ID in response: {data}")
        return None

    def create_carousel_container(self, text: str, media_urls: List[str]) -> Optional[str]:
        """Create a carousel container with multiple images"""
        if not media_urls or len(media_urls) == 0:
            logger.error("No media URLs provided for carousel")
            return None

        if len(media_urls) > 20:
            logger.warning(f"Carousel limited to 20 images, truncating from {len(media_urls)}")
            media_urls = media_urls[:20]

        # Step 1: Create individual media containers for each image
        media_container_ids = []
        for idx, media_url in enumerate(media_urls, 1):
            if not media_url:
                logger.warning(f"Skipping empty media URL at index {idx}")
                continue

            logger.info(f"Creating media container {idx}/{len(media_urls)}: {media_url}")
            container_id = self.create_media_container(media_url=media_url, is_carousel_item=True)

            if container_id:
                media_container_ids.append(container_id)
            else:
                logger.warning(f"Failed to create media container for image {idx}")

        if not media_container_ids:
            logger.error("No media containers created successfully")
            return None

        # Step 2: Create carousel container with all media IDs
        params = {
            'media_type': 'CAROUSEL',
            'children': ','.join(media_container_ids),
            'text': text,
            'access_token': self.access_token
        }

        data = self._make_request('POST', f"{self.user_id}/threads", params)

        if data and 'id' in data:
            carousel_id = data['id']
            logger.info(f"Created carousel container with {len(media_container_ids)} images: {carousel_id}")
            return carousel_id

        logger.error(f"No carousel container ID in response: {data}")
        return None

    def publish_container(self, container_id: str) -> bool:
        """Publish a media container as a Threads post

        POST /{threads-user-id}/threads_publish
        Required params: creation_id, access_token
        Returns: post ID
        """
        params = {
            'creation_id': container_id,
            'access_token': self.access_token
        }

        logger.info(f"Publishing container with creation_id: {container_id}")
        data = self._make_request('POST', f"{self.user_id}/threads_publish", params)

        if data and 'id' in data:
            post_id = data['id']
            logger.info(f"Successfully published post! Post ID: {post_id}")
            return True

        logger.error(f"Failed to publish. Response: {data}")
        return False

    def post_to_threads(self, text: str, media_urls: Optional[List[str]] = None) -> bool:
        """Create and publish a post to Threads (text-only, single image, or carousel)"""
        # If multiple images provided, create carousel post
        if media_urls and len(media_urls) > 1:
            return self.post_carousel_to_threads(text, media_urls)

        # Single image or text-only post
        single_image = media_urls[0] if media_urls and len(media_urls) == 1 else None
        container_id = self.create_media_container(text, media_url=single_image)
        if not container_id:
            return False

        time.sleep(Config.CONTAINER_PUBLISH_DELAY)
        return self.publish_container(container_id)

    def post_carousel_to_threads(self, text: str, media_urls: List[str]) -> bool:
        """Create and publish a carousel post to Threads with multiple images"""
        carousel_id = self.create_carousel_container(text, media_urls)
        if not carousel_id:
            return False

        time.sleep(Config.CONTAINER_PUBLISH_DELAY)
        return self.publish_container(carousel_id)

    def check_rate_limits(self) -> Dict:
        """Check current API rate limits"""
        params = {
            'fields': 'quota_usage,config',
            'access_token': self.access_token
        }

        data = self._make_request('GET', f"{self.user_id}/threads_publishing_limit", params)

        if data:
            logger.info(f"Rate limit status: {data}")
            return data
        return {}


# ============= POST MANAGER =============
class DealsPostManager:
    """Manages the process of fetching deals and posting to Threads"""

    def __init__(self, test_mode: bool = False):
        self.threads_api = ThreadsAPI() if not test_mode else None
        self.posted_deals_file = Config.POSTED_DEALS_FILE
        self.posted_deals = self._load_posted_deals()
        self.test_mode = test_mode

    def _load_posted_deals(self) -> List[str]:
        """Load previously posted deals to avoid duplicates"""
        if not os.path.exists(self.posted_deals_file):
            return []

        try:
            with open(self.posted_deals_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading posted deals: {e}")
            return []

    def _save_posted_deals(self):
        """Save posted deals to file"""
        self.posted_deals = self.posted_deals[-Config.MAX_POSTED_DEALS_HISTORY:]
        try:
            with open(self.posted_deals_file, 'w') as f:
                json.dump(self.posted_deals, f, indent=2)
        except IOError as e:
            logger.error(f"Error saving posted deals: {e}")

    def _filter_new_deals(self, deals: List[Deal]) -> List[Deal]:
        """Filter out previously posted deals"""
        new_deals = []
        for deal in deals:
            deal_id = deal.get_unique_id()
            if deal_id not in self.posted_deals:
                new_deals.append(deal)
        return new_deals

    def _mark_deals_as_posted(self, deals: List[Deal]):
        """Mark deals as posted by adding their IDs to the posted deals list"""
        for deal in deals:
            deal_id = deal.get_unique_id()
            if deal_id not in self.posted_deals:
                self.posted_deals.append(deal_id)

    def _format_deal_text(self, deal: Deal, index: int) -> str:
        """Format a single deal for posting without description"""
        emoji = Config.RANK_EMOJIS.get(index, f"{index}.")

        # Clean up title (remove extra info)
        title = deal.title.split(' - ')[0][:50]

        # Format price
        price_text = f"${deal.price}" if not deal.price.startswith('$') else deal.price
        discount_text = f" ({deal.discount_percentage} off)" if deal.discount_percentage else ""

        # Use short_link if available, otherwise use regular link
        link = deal.short_link if deal.short_link else deal.link

        # Format with blank line between products for better readability
        return f"{emoji} {title}\n💰 {price_text}{discount_text}\n👉 {link}"

    def create_post_content(self, deals: List[Deal]) -> str:
        """Create the full post content from a list of deals"""
        header = (
            f"🔥 TODAY'S HOTTEST DEALS 🔥\n"
            f"📅 {datetime.now().strftime('%B %d, %Y')}\n"
            f"{Config.SEPARATOR_LINE}\n\n"
        )

        deal_texts = [
            self._format_deal_text(deal, i)
            for i, deal in enumerate(deals[:Config.TOP_DEALS_COUNT], 1)
        ]

        footer = (
            f"\n{Config.SEPARATOR_LINE}\n"
            f"💡 Follow for daily deals!\n"
            f"#deals #savings #shopping #discounts"
        )

        # Join deals with double newline for spacing between products
        content = header + "\n\n".join(deal_texts) + footer

        # Truncate if too long
        if len(content) > Config.MAX_POST_LENGTH:
            content = content[:Config.MAX_POST_LENGTH - 3] + "..."

        return content

    async def fetch_and_post_deals(self):
        """Main function to fetch deals and post to Threads"""
        logger.info("Starting deals fetch and post process...")

        # Fetch deals
        async with DealsFetcher() as fetcher:
            deals = await fetcher.fetch_all_deals()

        if not deals:
            logger.warning("No deals fetched")
            return

        # Filter for Amazon deals only
        amazon_deals = [deal for deal in deals if deal.store.lower() == 'amazon']
        logger.info(f"Filtered {len(amazon_deals)} Amazon deals from {len(deals)} total deals")

        if not amazon_deals:
            logger.warning("No Amazon deals found")
            return

        # Filter new deals
        new_deals = self._filter_new_deals(amazon_deals)

        if not new_deals:
            logger.info("No new Amazon deals to post")
            return

        # Select top deals
        top_deals = new_deals[:Config.TOP_DEALS_COUNT]
        logger.info(f"Selected top {len(top_deals)} deals to post")

        # Create post content
        post_content = self.create_post_content(top_deals)
        logger.info(f"Post content ({len(post_content)} chars):\n{post_content}")

        # Collect image URLs from top deals
        media_urls = [deal.image_url for deal in top_deals if deal.image_url]
        if media_urls:
            logger.info(f"Found {len(media_urls)} images for carousel post")
        else:
            logger.info("No images found, posting text-only")

        # Post to Threads
        if self.test_mode:
            logger.info("TEST MODE: Skipping actual posting to Threads")
            success = True
        else:
            success = self.threads_api.post_to_threads(post_content, media_urls=media_urls if media_urls else None)

        if success:
            logger.info("Successfully posted deals to Threads!")
            # Mark only the deals that were actually posted
            self._mark_deals_as_posted(top_deals)
            self._save_posted_deals()
        else:
            logger.error("Failed to post deals to Threads")


# ============= MAIN ENTRY POINT =============
def validate_environment() -> bool:
    """Validate required environment variables are set"""
    required_vars = ['THREADS_ACCESS_TOKEN', 'THREADS_USER_ID']
    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        logger.error(f"Missing required environment variables: {missing}")
        return False
    return True


def main() -> int:
    """Main entry point - runs once when executed"""
    logger.info("=" * 50)
    logger.info("Starting Deals to Threads poster...")
    logger.info(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 50)

    # Check environment variables
    if not validate_environment():
        return 1

    try:
        # Determine if in test mode
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'

        # Create manager and run the posting process
        manager = DealsPostManager(test_mode=test_mode)
        asyncio.run(manager.fetch_and_post_deals())

        logger.info("=" * 50)
        logger.info("Successfully completed deals posting!")
        logger.info("=" * 50)
        return 0

    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())
