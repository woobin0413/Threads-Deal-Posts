"""
Automated Deals Fetcher and Threads Poster
This script fetches deals from free APIs and web scraping, then posts to Threads.
Designed to be run via Windows Task Scheduler or cron job.
"""

import os
import asyncio
import logging
import re
import time
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass

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
    TOP_DEALS_COUNT = 3
    MAX_TITLE_LENGTH = 100

    # Post Configuration
    MAX_POST_LENGTH = 2000  # Threads supports up to 500 chars per post, but we'll format nicely
    SEPARATOR_LINE = "─" * 30

    # File paths
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
    RANK_EMOJIS = {1: "🥇", 2: "🥈", 3: "🥉"}


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

    @staticmethod
    def extract_asin_from_url(url: str) -> Optional[str]:
        """Extract ASIN from Amazon URL"""
        if not url:
            return None
        # Pattern 1: /dp/ASIN/ or /dp/ASIN? or /dp/ASIN
        match = re.search(r'/dp/([A-Z0-9]{10})(?:[/?]|$)', url)
        if match:
            return match.group(1)
        # Pattern 2: /gp/product/ASIN/
        match = re.search(r'/gp/product/([A-Z0-9]{10})(?:[/?]|$)', url)
        if match:
            return match.group(1)
        # Pattern 3: /product/ASIN/
        match = re.search(r'/product/([A-Z0-9]{10})(?:[/?]|$)', url)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def create_affiliate_link(asin: str, affiliate_tag: str = None) -> str:
        """Create Amazon affiliate link from ASIN"""
        if not affiliate_tag:
            affiliate_tag = os.getenv('AMAZON_AFFILIATE_TAG', 'boostdeals20-20')
        return f"https://www.amazon.com/dp/{asin}?tag={affiliate_tag}"


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

        # Enhanced headers to avoid bot detection
        enhanced_headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        }

        for idx, short_link in enumerate(links, 1):
            try:
                async with self.session.get(short_link, headers=enhanced_headers, allow_redirects=True) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to fetch {short_link}: Status {response.status}")
                        continue

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Try multiple selectors for title
                    title = None
                    title_selectors = [
                        ('span', {'id': 'productTitle'}),
                        ('h1', {'id': 'title'}),
                        ('span', {'class': 'product-title-word-break'}),
                    ]
                    for tag, attrs in title_selectors:
                        elem = soup.find(tag, attrs)
                        if elem:
                            title = elem.get_text(strip=True)
                            break

                    if not title:
                        title = f"Amazon Deal {idx}"
                        logger.warning(f"Could not find title for {short_link}")

                    # Try multiple selectors for price
                    price = None
                    price_selectors = [
                        ('span', {'class': 'a-offscreen'}),
                        ('span', {'class': 'a-price-whole'}),
                        ('span', {'class': 'priceToPay'}),
                        ('span', {'id': 'priceblock_ourprice'}),
                        ('span', {'id': 'priceblock_dealprice'}),
                    ]
                    for tag, attrs in price_selectors:
                        elem = soup.find(tag, attrs)
                        if elem:
                            price = elem.get_text(strip=True)
                            break

                    if not price:
                        price = "See Deal"
                        logger.warning(f"Could not find price for {short_link}")

                    # Extract discount percentage
                    discount = None
                    discount_selectors = [
                        ('span', {'class': 'savingsPercentage'}),
                        ('span', {'class': 'a-size-large a-color-price savingPriceOverride'}),
                    ]
                    for tag, attrs in discount_selectors:
                        elem = soup.find(tag, attrs)
                        if elem:
                            discount = elem.get_text(strip=True)
                            break

                    # Try multiple selectors for product image
                    image_url = None
                    img_selectors = [
                        ('img', {'id': 'landingImage'}),
                        ('img', {'id': 'imgBlkFront'}),
                        ('img', {'class': 'a-dynamic-image'}),
                    ]
                    for tag, attrs in img_selectors:
                        elem = soup.find(tag, attrs)
                        if elem:
                            image_url = elem.get('src') or elem.get('data-old-hires')
                            if image_url:
                                break

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

                    # Clean up price
                    if price and price != "See Deal":
                        price = price.replace('$', '').replace(',', '').strip()

                    deal = Deal(
                        title=title[:Config.MAX_TITLE_LENGTH],
                        price=price,
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

    async def fetch_slickdeals_amazon(self, min_thumbs_up: int = 100, max_deals: int = 10) -> List[Deal]:
        """Fetch Amazon deals from Slickdeals with minimum thumbs up"""
        deals = []

        # Try multiple pages to find enough deals
        urls = [
            "https://slickdeals.net/",
            "https://slickdeals.net/?page=2",
            "https://slickdeals.net/?page=3"
        ]

        logger.info(f"Fetching Amazon deals from Slickdeals with {min_thumbs_up}+ thumbs up...")

        for url in urls:
            try:
                async with self.session.get(url, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        continue

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Find all deal cards
                    deal_cards = soup.find_all('div', class_='dealCard') or \
                                soup.find_all('li', class_='fpGridBox') or \
                                soup.find_all('div', attrs={'data-role': 'dealCard'})

                    logger.info(f"   Found {len(deal_cards)} deal cards on {url}")

                    for card in deal_cards:
                        try:
                            # Extract link first to check if it's Amazon
                            links_in_card = card.find_all('a')
                            if len(links_in_card) < 2:
                                continue

                            title_elem = links_in_card[1]
                            title = title_elem.get_text(strip=True)
                            slickdeals_link = title_elem.get('href', '')

                            if slickdeals_link and not slickdeals_link.startswith('http'):
                                slickdeals_link = f"https://slickdeals.net{slickdeals_link}"

                            # Check if deal is for Amazon
                            is_amazon = False

                            # Check store link (try multiple class patterns)
                            store_elem = card.find('a', class_=lambda x: x and ('merchant' in str(x).lower() or 'store' in str(x).lower()))
                            if store_elem and 'amazon' in store_elem.get_text(strip=True).lower():
                                is_amazon = True

                            # Check if title mentions Amazon
                            if 'amazon' in title.lower():
                                is_amazon = True

                            if not is_amazon:
                                continue

                            # Extract thumbs up count
                            thumbs_elem = card.find('span', class_='dealCardSocialControls__voteCount')
                            thumbs_up = 0
                            if thumbs_elem:
                                thumbs_text = thumbs_elem.get_text(strip=True)
                                match = re.search(r'\d+', thumbs_text)
                                if match:
                                    thumbs_up = int(match.group())

                            # Skip if below threshold
                            if thumbs_up < min_thumbs_up:
                                continue

                            # Extract price
                            price_elem = card.find('span', class_='dealCard__price')
                            price = price_elem.get_text(strip=True) if price_elem else "See Deal"

                            # Extract original price
                            original_price_elem = card.find('span', class_='dealCard__originalPrice')
                            original_price = original_price_elem.get_text(strip=True) if original_price_elem else None

                            # Calculate discount
                            discount = None
                            if original_price and price != "See Deal":
                                try:
                                    price_num = float(price.replace('$', '').replace(',', ''))
                                    orig_num = float(original_price.replace('$', '').replace(',', ''))
                                    discount_pct = int((1 - price_num/orig_num) * 100)
                                    discount = f"-{discount_pct}%"
                                except:
                                    pass

                            # Extract image
                            img_elems = card.find_all('img')
                            image_url = None
                            for img in img_elems:
                                src = img.get('src') or img.get('data-src')
                                if src and 'avatar' not in src.lower():
                                    image_url = src
                                    if not image_url.startswith('http'):
                                        image_url = f"https:{image_url}" if image_url.startswith('//') else f"https://slickdeals.net{image_url}"
                                    break

                            # We need to get the actual Amazon URL from the Slickdeals page
                            # For now, store the Slickdeals link and we'll extract later if needed
                            deal = Deal(
                                title=title[:Config.MAX_TITLE_LENGTH],
                                price=price.replace('$', '').strip() if price != "See Deal" else price,
                                original_price=original_price,
                                discount_percentage=discount,
                                store="Amazon",
                                link=slickdeals_link,  # This will be converted to affiliate link
                                image_url=image_url,
                                description=None,
                                score=thumbs_up
                            )

                            deals.append(deal)
                            logger.info(f"   ✓ Found: {title[:60]}... (👍 {thumbs_up})")
                            logger.info(f"      Link: {slickdeals_link}")

                            if len(deals) >= max_deals:
                                break

                        except Exception as e:
                            logger.debug(f"Error parsing deal card: {e}")
                            continue

                    if len(deals) >= max_deals:
                        break

            except Exception as e:
                logger.warning(f"Error scraping {url}: {e}")
                continue

        # Sort by thumbs up descending
        deals.sort(key=lambda x: x.score, reverse=True)
        logger.info(f"Successfully fetched {len(deals)} Amazon deals from Slickdeals")

        return deals[:max_deals]

    async def fetch_all_deals(self) -> List[Deal]:
        """Fetch deals from links file, Slickdeals, or Reddit"""
        # Priority 1: Check if links file exists and has content
        if os.path.exists(Config.DEALS_LINKS_FILE):
            with open(Config.DEALS_LINKS_FILE, 'r') as f:
                links = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]

            if links:
                logger.info(f"Using deals from {Config.DEALS_LINKS_FILE}")
                deals = await self.fetch_amazon_from_links()
                return deals

        # Priority 2: Fetch from Slickdeals
        logger.info("Fetching deals from Slickdeals...")
        deals = await self.fetch_slickdeals_amazon(min_thumbs_up=100, max_deals=20)

        if deals:
            return deals

        # Priority 3: Fallback to Reddit
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
                # Small delay between creating media containers
                time.sleep(0.5)
            else:
                logger.warning(f"Failed to create media container for image {idx}")

        if not media_container_ids:
            logger.error("No media containers created successfully")
            return None

        # Step 2: Create carousel container with all media IDs immediately after
        # (without additional delay to avoid container expiration)
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
        self.test_mode = test_mode

    def _format_deal_text(self, deal: Deal, index: int) -> str:
        """Format a single deal for posting without description"""
        emoji = Config.RANK_EMOJIS.get(index, f"{index}.")

        # Use full title (already truncated to MAX_TITLE_LENGTH=100 when created)
        title = deal.title

        # Format price
        price_text = f"${deal.price}" if not deal.price.startswith('$') else deal.price
        discount_text = f" ({deal.discount_percentage} off)" if deal.discount_percentage else ""

        # Use short_link if available, otherwise use regular link
        link = deal.short_link if deal.short_link else deal.link

        # Format with blank line between products for better readability
        return f"{emoji} {title}\n💰 {price_text}{discount_text}\n👉 {link}"

    def _truncate_at_word(self, text: str, max_length: int) -> str:
        """Truncate text at word boundary, ensuring clean cutoff"""
        if len(text) <= max_length:
            return text

        # Find the last space before max_length
        truncated = text[:max_length]
        last_space = truncated.rfind(' ')

        if last_space > max_length * 0.7:  # Only use word boundary if it's reasonably close
            return text[:last_space].rstrip(',')
        return truncated.rstrip(',')

    def create_post_content(self, deals: List[Deal]) -> str:
        """Create the full post content from a list of deals"""
        header = f"🔥 TODAY'S HOTTEST DEALS 🔥\n📅 {datetime.now().strftime('%B %d, %Y')}\n\n"
        footer = f"\n💡 Follow for daily deals!\n#AmazonDeals #AmazonGadgets #Deals #Savings"
        footer_short = f"\n#AmazonDeals #Deals #Savings"

        max_length = 500

        # First try with full titles
        deal_texts = [
            self._format_deal_text(deal, i)
            for i, deal in enumerate(deals[:Config.TOP_DEALS_COUNT], 1)
        ]
        content = header + "\n\n".join(deal_texts) + footer

        # If too long, try shorter footer
        if len(content) > max_length:
            content = header + "\n\n".join(deal_texts) + footer_short

        # If still too long, truncate titles proportionally at word boundaries
        if len(content) > max_length:
            available_space = max_length - len(header) - len(footer_short) - (len(deals) * 2 * 2)  # account for \n\n between deals
            # Calculate space per deal
            price_link_overhead = 50  # approximate chars for price and link per deal
            title_space_per_deal = (available_space // len(deals)) - price_link_overhead
            title_space_per_deal = max(40, title_space_per_deal)  # minimum 40 chars per title

            # Recreate deal texts with truncated titles at word boundaries
            truncated_deal_texts = []
            for i, deal in enumerate(deals[:Config.TOP_DEALS_COUNT], 1):
                emoji = Config.RANK_EMOJIS.get(i, f"{i}.")
                title = self._truncate_at_word(deal.title, title_space_per_deal)
                price_text = f"${deal.price}" if not deal.price.startswith('$') else deal.price
                discount_text = f" ({deal.discount_percentage} off)" if deal.discount_percentage else ""
                link = deal.short_link if deal.short_link else deal.link
                truncated_deal_texts.append(f"{emoji} {title}\n💰 {price_text}{discount_text}\n👉 {link}")

            content = header + "\n\n".join(truncated_deal_texts) + footer_short

        return content

    def _extract_amazon_url_from_slickdeals(self, slickdeals_url: str) -> Optional[str]:
        """Extract Amazon URL from Slickdeals page"""
        try:
            headers = {
                'User-Agent': Config.USER_AGENT,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
            }
            response = requests.get(slickdeals_url, headers=headers, timeout=10, allow_redirects=True)
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for Slickdeals click tracking links that go to Amazon
            slickdeals_click_links = soup.find_all('a', href=re.compile(r'slickdeals\.net/click'))
            for link in slickdeals_click_links:
                href = link.get('href')
                if href:
                    # Follow the Slickdeals redirect to get actual Amazon URL
                    try:
                        redirect_response = requests.head(href, headers=headers, timeout=5, allow_redirects=True)
                        final_url = redirect_response.url
                        if 'amazon.com' in final_url or 'amzn.to' in final_url:
                            logger.info(f"   Found Amazon URL via redirect: {final_url[:80]}...")
                            return final_url
                    except:
                        continue

            # Fallback: look for direct Amazon links (less common)
            amazon_links = soup.find_all('a', href=re.compile(r'amazon\.com|amzn\.to'))
            if amazon_links:
                amazon_url = amazon_links[0].get('href')
                if amazon_url and ('amazon.com' in amazon_url or 'amzn.to' in amazon_url):
                    return amazon_url

            return None
        except Exception as e:
            logger.warning(f"Error extracting Amazon URL from Slickdeals: {e}")
            return None

    def _convert_to_affiliate_link(self, deal: Deal) -> Optional[Deal]:
        """Convert deal link to Amazon affiliate link if possible

        Returns:
            NEW Deal object with affiliate link if successful, None if ASIN extraction failed
            Original deal object is NOT modified (for logging purposes)
        """
        from copy import deepcopy

        # Create a copy so we don't modify the original deal (for logging)
        deal_copy = deepcopy(deal)
        amazon_url = deal_copy.link

        # If it's a Slickdeals link, extract the Amazon URL first
        if 'slickdeals.net' in deal_copy.link.lower():
            logger.info(f"   Extracting Amazon URL from Slickdeals page...")
            extracted_url = self._extract_amazon_url_from_slickdeals(deal_copy.link)
            if extracted_url:
                amazon_url = extracted_url
            else:
                logger.warning(f"   Could not extract Amazon URL from Slickdeals - skipping deal")
                return None

        # Extract ASIN and create affiliate link
        if 'amazon.com' in amazon_url.lower() or 'amzn.to' in amazon_url.lower():
            asin = TextExtractor.extract_asin_from_url(amazon_url)
            if asin:
                affiliate_link = TextExtractor.create_affiliate_link(asin)
                logger.info(f"   ✅ Converted to affiliate link: ASIN={asin}")
                deal_copy.link = affiliate_link
                deal_copy.short_link = affiliate_link
                return deal_copy
            else:
                logger.warning(f"   ❌ Could not extract ASIN from: {amazon_url} - skipping deal")
                return None

        # If not an Amazon URL, skip it
        logger.warning(f"   ❌ Not an Amazon URL: {amazon_url} - skipping deal")
        return None

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

        # Sort by score ascending (lowest likes first) and select top 3
        amazon_deals.sort(key=lambda x: x.score)
        top_deals = amazon_deals[:Config.TOP_DEALS_COUNT]
        logger.info(f"Selected top {len(top_deals)} deals to post (sorted by least likes)")

        # Log original deals with Slickdeals links
        logger.info("Original deals (with Slickdeals links):")
        for i, deal in enumerate(top_deals, 1):
            logger.info(f"  {i}. {deal.title[:60]}... (👍 {deal.score})")
            logger.info(f"     Original link: {deal.link}")

        # Convert all links to affiliate links and filter out deals without valid ASINs
        logger.info("Converting links to Amazon affiliate links...")
        converted_deals = []
        for deal in top_deals:
            converted_deal = self._convert_to_affiliate_link(deal)
            if converted_deal:
                converted_deals.append(converted_deal)

        top_deals = converted_deals
        logger.info(f"Successfully converted {len(top_deals)} deals to affiliate links")

        # If no valid deals with ASINs found, don't post
        if not top_deals:
            logger.warning("No deals with valid Amazon ASINs found - skipping post")
            return

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
