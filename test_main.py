"""
Tests for the Automated Deals Fetcher and Threads Poster
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock, mock_open
from datetime import datetime
import os

from main import (
    Deal,
    DealsFetcher,
    ThreadsAPI,
    DealsPostManager
)


# ========== Fixtures ==========

@pytest.fixture
def sample_deal():
    """Create a sample Deal object for testing"""
    return Deal(
        title="Test Product",
        price="$29.99",
        original_price="$49.99",
        discount_percentage="40%",
        store="Test Store",
        link="https://example.com/deal",
        image_url="https://example.com/image.jpg",
        description="Test description",
        score=85
    )


@pytest.fixture
def sample_deals():
    """Create a list of sample deals"""
    return [
        Deal(
            title="Gaming Mouse",
            price="$19.99",
            original_price="$49.99",
            discount_percentage="60%",
            store="Amazon",
            link="https://amazon.com/mouse",
            image_url="https://example.com/mouse.jpg",
            description="RGB Gaming Mouse",
            score=90
        ),
        Deal(
            title="Mechanical Keyboard",
            price="$79.99",
            original_price="$129.99",
            discount_percentage="38%",
            store="Best Buy",
            link="https://bestbuy.com/keyboard",
            image_url="https://example.com/keyboard.jpg",
            description="RGB Mechanical Keyboard",
            score=85
        ),
        Deal(
            title="USB Cable",
            price="$5.99",
            original_price="$9.99",
            discount_percentage="40%",
            store="Walmart",
            link="https://walmart.com/cable",
            image_url=None,
            description="USB-C Cable",
            score=70
        )
    ]


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables"""
    monkeypatch.setenv('THREADS_ACCESS_TOKEN', 'test_access_token')
    monkeypatch.setenv('THREADS_USER_ID', 'test_user_id')
    monkeypatch.setenv('USE_DUMMY_DATA', 'false')


# ========== Deal Tests ==========

class TestDeal:
    """Test the Deal dataclass"""

    def test_deal_creation(self, sample_deal):
        """Test creating a Deal object"""
        assert sample_deal.title == "Test Product"
        assert sample_deal.price == "$29.99"
        assert sample_deal.original_price == "$49.99"
        assert sample_deal.discount_percentage == "40%"
        assert sample_deal.store == "Test Store"
        assert sample_deal.link == "https://example.com/deal"
        assert sample_deal.image_url == "https://example.com/image.jpg"
        assert sample_deal.description == "Test description"
        assert sample_deal.score == 85

    def test_deal_optional_fields(self):
        """Test Deal with optional fields as None"""
        deal = Deal(
            title="Minimal Deal",
            price="$10.00",
            original_price=None,
            discount_percentage=None,
            store="Store",
            link="https://example.com",
            image_url=None,
            description=None,
            score=50
        )
        assert deal.original_price is None
        assert deal.discount_percentage is None
        assert deal.image_url is None
        assert deal.description is None

    def test_deal_default_score(self):
        """Test that Deal has default score of 0"""
        deal = Deal(
            title="No Score Deal",
            price="$10.00",
            original_price=None,
            discount_percentage=None,
            store="Store",
            link="https://example.com",
            image_url=None,
            description=None
        )
        assert deal.score == 0


# ========== DealsFetcher Tests ==========

class TestDealsFetcher:
    """Test the DealsFetcher class"""

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test DealsFetcher context manager creates and closes session"""
        async with DealsFetcher() as fetcher:
            assert fetcher.session is not None

    @pytest.mark.asyncio
    async def test_fetch_cheapshark_deals_success(self):
        """Test successful fetch from CheapShark API"""
        mock_response_data = [
            {
                'title': 'Test Game',
                'salePrice': '9.99',
                'normalPrice': '29.99',
                'dealID': 'test123',
                'storeName': 'Steam',
                'thumb': 'https://example.com/thumb.jpg',
                'metacriticScore': '85',
                'dealRating': '9.5'
            }
        ]

        async with DealsFetcher() as fetcher:
            with patch.object(fetcher.session, 'get') as mock_get:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=mock_response_data)
                mock_get.return_value.__aenter__.return_value = mock_response

                deals = await fetcher.fetch_cheapshark_deals()

                assert len(deals) == 1
                assert deals[0].title == 'Test Game (PC Game)'
                assert deals[0].price == '$9.99'
                assert deals[0].original_price == '$29.99'
                assert deals[0].store == 'Steam'
                assert deals[0].score == 95  # dealRating 9.5 * 10

    @pytest.mark.asyncio
    async def test_fetch_cheapshark_deals_error(self):
        """Test CheapShark API error handling"""
        async with DealsFetcher() as fetcher:
            with patch.object(fetcher.session, 'get') as mock_get:
                mock_response = AsyncMock()
                mock_response.status = 500
                mock_get.return_value.__aenter__.return_value = mock_response

                deals = await fetcher.fetch_cheapshark_deals()

                assert deals == []

    @pytest.mark.asyncio
    async def test_fetch_dummy_api_deals_success(self):
        """Test successful fetch from DummyJSON API"""
        mock_response_data = {
            'products': [
                {
                    'title': 'Test Product',
                    'price': 100,
                    'discountPercentage': 20,
                    'brand': 'TestBrand',
                    'thumbnail': 'https://example.com/thumb.jpg',
                    'description': 'A test product description',
                    'rating': 4.5
                }
            ]
        }

        async with DealsFetcher() as fetcher:
            with patch.object(fetcher.session, 'get') as mock_get:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=mock_response_data)
                mock_get.return_value.__aenter__.return_value = mock_response

                deals = await fetcher.fetch_dummy_api_deals()

                assert len(deals) == 1
                assert deals[0].title == 'Test Product'
                assert deals[0].price == '$80.00'  # $100 - 20%
                assert deals[0].original_price == '$100.00'
                assert deals[0].discount_percentage == '20%'
                assert deals[0].store == 'TestBrand'
                assert deals[0].score == 90  # rating 4.5 * 20

    @pytest.mark.asyncio
    async def test_fetch_reddit_deals_success(self):
        """Test successful fetch from Reddit API"""
        mock_response_data = {
            'data': {
                'children': [
                    {
                        'data': {
                            'title': '[Deal] Test Product $19.99',
                            'url': 'https://www.amazon.com/product',
                            'score': 150,
                            'promoted': False,
                            'is_sponsored': False
                        }
                    }
                ]
            }
        }

        async with DealsFetcher() as fetcher:
            with patch.object(fetcher.session, 'get') as mock_get:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=mock_response_data)
                mock_get.return_value.__aenter__.return_value = mock_response

                deals = await fetcher.fetch_reddit_deals()

                assert len(deals) == 1
                assert '$19.99' in deals[0].title
                assert deals[0].price == '$19.99'
                assert deals[0].store == 'Amazon'
                assert deals[0].score == 150

    @pytest.mark.asyncio
    async def test_fetch_reddit_deals_with_images(self):
        """Test fetching Reddit deals with preview images and thumbnails"""
        mock_response_data = {
            'data': {
                'children': [
                    {
                        'data': {
                            'title': '[Deal] Samsung 65" TV $499',
                            'url': 'https://www.amazon.com/tv',
                            'score': 250,
                            'promoted': False,
                            'preview': {
                                'images': [
                                    {
                                        'source': {
                                            'url': 'https://preview.redd.it/image1.jpg?format=jpg&amp;auto=webp&amp;s=abc123'
                                        }
                                    }
                                ]
                            },
                            'thumbnail': 'https://b.thumbs.redditmedia.com/thumb1.jpg'
                        }
                    },
                    {
                        'data': {
                            'title': '[Deal] AirPods Pro $189',
                            'url': 'https://www.bestbuy.com/airpods',
                            'score': 180,
                            'promoted': False,
                            'thumbnail': 'https://b.thumbs.redditmedia.com/thumb2.jpg'
                        }
                    },
                    {
                        'data': {
                            'title': '[SPONSORED] Promoted Product',
                            'url': 'https://example.com/promo',
                            'score': 500,
                            'promoted': True
                        }
                    }
                ]
            }
        }

        async with DealsFetcher() as fetcher:
            with patch.object(fetcher.session, 'get') as mock_get:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=mock_response_data)
                mock_get.return_value.__aenter__.return_value = mock_response

                deals = await fetcher.fetch_reddit_deals()

                # Should only get 2 deals (promoted one filtered out)
                assert len(deals) == 2

                # First deal should have preview image (unescaped)
                assert deals[0].image_url == 'https://preview.redd.it/image1.jpg?format=jpg&auto=webp&s=abc123'
                assert deals[0].title == '[Deal] Samsung 65" TV $499'

                # Second deal should have thumbnail
                assert deals[1].image_url == 'https://b.thumbs.redditmedia.com/thumb2.jpg'
                assert deals[1].title == '[Deal] AirPods Pro $189'

    @pytest.mark.asyncio
    async def test_fetch_all_deals(self):
        """Test fetching from all sources concurrently"""
        async with DealsFetcher() as fetcher:
            with patch.object(fetcher, 'fetch_reddit_deals', return_value=[
                Deal("Deal 1", "$10", None, None, "Store1", "http://link1", None, None, 100),
                Deal("Deal 2", "$20", None, None, "Store2", "http://link2", None, None, 90)
            ]):
                deals = await fetcher.fetch_all_deals()

                assert len(deals) > 0
                # Check that deals are sorted by score
                for i in range(len(deals) - 1):
                    assert deals[i].score >= deals[i + 1].score

    @pytest.mark.asyncio
    async def test_fetch_all_deals_removes_duplicates(self):
        """Test that fetch_all_deals removes duplicate deals"""
        duplicate_deals = [
            Deal("Test Product", "$10", None, None, "Store1", "http://link1", None, None, 100),
            Deal("Test Product!!!", "$10", None, None, "Store2", "http://link2", None, None, 90),
        ]

        async with DealsFetcher() as fetcher:
            with patch.object(fetcher, 'fetch_reddit_deals', return_value=duplicate_deals):
                deals = await fetcher.fetch_all_deals()

                # Should remove duplicates based on normalized title
                assert len(deals) == 1


# ========== ThreadsAPI Tests ==========

class TestThreadsAPI:
    """Test the ThreadsAPI class"""

    def test_init_success(self, mock_env_vars):
        """Test successful ThreadsAPI initialization"""
        api = ThreadsAPI()
        assert api.access_token == 'test_access_token'
        assert api.user_id == 'test_user_id'
        assert api.api_base == "https://graph.threads.net/v1.0"

    def test_init_missing_token(self, monkeypatch):
        """Test ThreadsAPI initialization fails without token"""
        monkeypatch.delenv('THREADS_ACCESS_TOKEN', raising=False)
        monkeypatch.setenv('THREADS_USER_ID', 'test_user_id')

        with pytest.raises(ValueError, match="THREADS_ACCESS_TOKEN and THREADS_USER_ID must be set"):
            ThreadsAPI()

    def test_create_media_container_success(self, mock_env_vars):
        """Test successful media container creation"""
        api = ThreadsAPI()

        mock_response = Mock()
        mock_response.json.return_value = {'id': 'container123'}
        mock_response.raise_for_status = Mock()

        with patch('requests.post', return_value=mock_response) as mock_post:
            container_id = api.create_media_container("Test post")

            assert container_id == 'container123'
            mock_post.assert_called_once()

    def test_create_media_container_with_image(self, mock_env_vars):
        """Test media container creation with image"""
        api = ThreadsAPI()

        mock_response = Mock()
        mock_response.json.return_value = {'id': 'container456'}
        mock_response.raise_for_status = Mock()

        with patch('requests.post', return_value=mock_response) as mock_post:
            container_id = api.create_media_container("Test post", "https://example.com/image.jpg")

            assert container_id == 'container456'
            # Verify image parameters were included
            call_params = mock_post.call_args[1]['params']
            assert call_params['media_type'] == 'IMAGE'
            assert call_params['image_url'] == 'https://example.com/image.jpg'

    def test_create_media_container_error(self, mock_env_vars):
        """Test media container creation error handling"""
        api = ThreadsAPI()

        with patch('requests.post', side_effect=Exception("API Error")):
            container_id = api.create_media_container("Test post")

            assert container_id is None

    def test_create_carousel_container_success(self, mock_env_vars):
        """Test creating a carousel container with multiple images"""
        api = ThreadsAPI()

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        # Mock responses for individual media containers
        def mock_post_side_effect(url, params):
            response = Mock()
            response.raise_for_status = Mock()
            if 'media_type' in params and params['media_type'] == 'IMAGE':
                # Individual image container
                response.json.return_value = {'id': f'media_{params["image_url"][-10:]}'}
            elif 'media_type' in params and params['media_type'] == 'CAROUSEL':
                # Carousel container
                response.json.return_value = {'id': 'carousel_123'}
            return response

        with patch('requests.post', side_effect=mock_post_side_effect) as mock_post:
            media_urls = [
                'https://example.com/image1.jpg',
                'https://example.com/image2.jpg',
                'https://example.com/image3.jpg'
            ]
            carousel_id = api.create_carousel_container("Deal post with images", media_urls)

            assert carousel_id == 'carousel_123'
            # Should make 4 calls: 3 for individual images + 1 for carousel
            assert mock_post.call_count == 4

    def test_create_carousel_container_no_images(self, mock_env_vars):
        """Test carousel creation fails with no images"""
        api = ThreadsAPI()

        carousel_id = api.create_carousel_container("Text only", [])

        assert carousel_id is None

    def test_post_to_threads_with_carousel(self, mock_env_vars):
        """Test posting with multiple images creates carousel"""
        api = ThreadsAPI()

        media_urls = [
            'https://example.com/img1.jpg',
            'https://example.com/img2.jpg',
            'https://example.com/img3.jpg'
        ]

        with patch.object(api, 'post_carousel_to_threads', return_value=True) as mock_carousel:
            with patch('time.sleep'):
                result = api.post_to_threads("Deal text", media_urls=media_urls)

                assert result is True
                mock_carousel.assert_called_once_with("Deal text", media_urls)

    def test_post_to_threads_with_single_image(self, mock_env_vars):
        """Test posting with single image"""
        api = ThreadsAPI()

        media_urls = ['https://example.com/single.jpg']

        with patch.object(api, 'create_media_container', return_value='container_123') as mock_create:
            with patch.object(api, 'publish_container', return_value=True):
                with patch('time.sleep'):
                    result = api.post_to_threads("Deal text", media_urls=media_urls)

                    assert result is True
                    mock_create.assert_called_once_with("Deal text", media_url='https://example.com/single.jpg')

    def test_publish_container_success(self, mock_env_vars):
        """Test successful container publishing"""
        api = ThreadsAPI()

        mock_response = Mock()
        mock_response.json.return_value = {'id': 'post123'}
        mock_response.raise_for_status = Mock()

        with patch('requests.post', return_value=mock_response):
            result = api.publish_container('container123')

            assert result is True

    def test_publish_container_error(self, mock_env_vars):
        """Test container publishing error handling"""
        api = ThreadsAPI()

        with patch('requests.post', side_effect=Exception("Publish Error")):
            result = api.publish_container('container123')

            assert result is False

    def test_post_to_threads_success(self, mock_env_vars):
        """Test successful end-to-end posting"""
        api = ThreadsAPI()

        with patch.object(api, 'create_media_container', return_value='container123'):
            with patch.object(api, 'publish_container', return_value=True):
                with patch('time.sleep'):  # Mock sleep to speed up test
                    result = api.post_to_threads("Test post")

                    assert result is True

    def test_post_to_threads_container_creation_fails(self, mock_env_vars):
        """Test posting fails when container creation fails"""
        api = ThreadsAPI()

        with patch.object(api, 'create_media_container', return_value=None):
            result = api.post_to_threads("Test post")

            assert result is False

    def test_check_rate_limits_success(self, mock_env_vars):
        """Test checking rate limits"""
        api = ThreadsAPI()

        mock_response = Mock()
        mock_response.json.return_value = {'quota_usage': 5, 'config': {'quota_total': 100}}
        mock_response.raise_for_status = Mock()

        with patch('requests.get', return_value=mock_response):
            result = api.check_rate_limits()

            assert result == {'quota_usage': 5, 'config': {'quota_total': 100}}

    def test_check_rate_limits_error(self, mock_env_vars):
        """Test rate limit check error handling"""
        api = ThreadsAPI()

        with patch('requests.get', side_effect=Exception("Rate limit error")):
            result = api.check_rate_limits()

            assert result == {}


# ========== DealsPostManager Tests ==========

class TestDealsPostManager:
    """Test the DealsPostManager class"""

    def test_init(self, mock_env_vars):
        """Test DealsPostManager initialization"""
        with patch('os.path.exists', return_value=False):
            manager = DealsPostManager()

            assert manager.threads_api is not None
            assert manager.posted_deals == []
            assert manager.posted_deals_file == 'posted_deals.json'

    def test_load_posted_deals_file_exists(self, mock_env_vars):
        """Test loading existing posted deals"""
        mock_deals = ['deal1', 'deal2', 'deal3']

        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(mock_deals))):
                manager = DealsPostManager()

                assert manager.posted_deals == mock_deals

    def test_load_posted_deals_file_not_exists(self, mock_env_vars):
        """Test loading when file doesn't exist"""
        with patch('os.path.exists', return_value=False):
            manager = DealsPostManager()

            assert manager.posted_deals == []

    def test_save_posted_deals(self, mock_env_vars):
        """Test saving posted deals to file"""
        with patch('os.path.exists', return_value=False):
            manager = DealsPostManager()
            manager.posted_deals = ['deal1', 'deal2']

            m = mock_open()
            with patch('builtins.open', m):
                manager.save_posted_deals()

                m.assert_called_once_with('posted_deals.json', 'w')

    def test_save_posted_deals_limits_size(self, mock_env_vars):
        """Test that save_posted_deals keeps only last 100 deals"""
        with patch('os.path.exists', return_value=False):
            manager = DealsPostManager()
            manager.posted_deals = [f'deal{i}' for i in range(150)]

            m = mock_open()
            with patch('builtins.open', m):
                manager.save_posted_deals()

                assert len(manager.posted_deals) == 100

    def test_format_deal_text(self, mock_env_vars, sample_deal):
        """Test formatting a single deal"""
        with patch('os.path.exists', return_value=False):
            manager = DealsPostManager()

            text = manager.format_deal_text(sample_deal, 1)

            assert "🥇" in text
            assert sample_deal.title in text
            assert sample_deal.price in text
            assert sample_deal.discount_percentage in text
            assert sample_deal.store in text
            assert sample_deal.link in text

    def test_format_deal_text_different_indices(self, mock_env_vars, sample_deal):
        """Test formatting deals with different emoji indices"""
        with patch('os.path.exists', return_value=False):
            manager = DealsPostManager()

            assert "🥇" in manager.format_deal_text(sample_deal, 1)
            assert "🥈" in manager.format_deal_text(sample_deal, 2)
            assert "🥉" in manager.format_deal_text(sample_deal, 3)
            assert "4️⃣" in manager.format_deal_text(sample_deal, 4)
            assert "5️⃣" in manager.format_deal_text(sample_deal, 5)

    def test_create_post_content(self, mock_env_vars, sample_deals):
        """Test creating full post content"""
        with patch('os.path.exists', return_value=False):
            manager = DealsPostManager()

            content = manager.create_post_content(sample_deals)

            assert "TODAY'S HOTTEST DEALS" in content
            assert "#deals #savings #shopping #discounts" in content
            assert "Follow for daily deals" in content

    def test_create_post_content_truncates_long_content(self, mock_env_vars):
        """Test that post content is truncated to 500 chars"""
        # Create many deals to exceed character limit
        many_deals = [
            Deal(
                title=f"Very Long Product Name That Takes Up Many Characters Number {i}",
                price="$99.99",
                original_price="$199.99",
                discount_percentage="50%",
                store="Store Name",
                link=f"https://example.com/very/long/url/that/takes/up/characters/{i}",
                image_url=None,
                description="Long description",
                score=90
            ) for i in range(10)
        ]

        with patch('os.path.exists', return_value=False):
            manager = DealsPostManager()

            content = manager.create_post_content(many_deals)

            assert len(content) <= 500
            if len(content) == 500:
                assert content.endswith("...")

    @pytest.mark.asyncio
    async def test_fetch_and_post_deals_success(self, mock_env_vars, sample_deals):
        """Test successful fetch and post process"""
        with patch('os.path.exists', return_value=False):
            manager = DealsPostManager()

            with patch.object(manager.threads_api, 'check_rate_limits', return_value={}):
                with patch.object(manager.threads_api, 'post_to_threads', return_value=True):
                    with patch('main.DealsFetcher') as MockFetcher:
                        mock_fetcher_instance = AsyncMock()
                        mock_fetcher_instance.fetch_all_deals = AsyncMock(return_value=sample_deals)
                        MockFetcher.return_value.__aenter__.return_value = mock_fetcher_instance

                        await manager.fetch_and_post_deals()

                        # Verify deals were saved
                        assert len(manager.posted_deals) > 0

    @pytest.mark.asyncio
    async def test_fetch_and_post_deals_no_deals(self, mock_env_vars):
        """Test when no deals are fetched"""
        with patch('os.path.exists', return_value=False):
            manager = DealsPostManager()

            with patch.object(manager.threads_api, 'check_rate_limits', return_value={}):
                with patch('main.DealsFetcher') as MockFetcher:
                    mock_fetcher_instance = AsyncMock()
                    mock_fetcher_instance.fetch_all_deals = AsyncMock(return_value=[])
                    MockFetcher.return_value.__aenter__.return_value = mock_fetcher_instance

                    await manager.fetch_and_post_deals()

                    # No deals should be posted
                    assert len(manager.posted_deals) == 0

    @pytest.mark.asyncio
    async def test_fetch_and_post_deals_filters_duplicates(self, mock_env_vars, sample_deals):
        """Test that previously posted deals are filtered out"""
        with patch('os.path.exists', return_value=False):
            manager = DealsPostManager()
            # Mark first deal as already posted
            manager.posted_deals = ['Amazon_Gaming Mouse']

            with patch.object(manager.threads_api, 'check_rate_limits', return_value={}):
                with patch.object(manager.threads_api, 'post_to_threads', return_value=True):
                    with patch('main.DealsFetcher') as MockFetcher:
                        mock_fetcher_instance = AsyncMock()
                        mock_fetcher_instance.fetch_all_deals = AsyncMock(return_value=sample_deals)
                        MockFetcher.return_value.__aenter__.return_value = mock_fetcher_instance

                        await manager.fetch_and_post_deals()

                        # Should have filtered out the duplicate
                        assert len(manager.posted_deals) > 1


# ========== Integration Tests ==========

class TestIntegration:
    """Integration tests for the full workflow"""

    @pytest.mark.asyncio
    async def test_full_workflow(self, mock_env_vars):
        """Test the complete workflow from fetch to post"""
        sample_deals = [
            Deal("Product 1", "$10", "$20", "50%", "Store1", "http://link1", None, None, 100),
            Deal("Product 2", "$15", "$25", "40%", "Store2", "http://link2", None, None, 90),
        ]

        with patch('os.path.exists', return_value=False):
            manager = DealsPostManager()

            with patch.object(manager.threads_api, 'check_rate_limits', return_value={'quota_usage': 5}):
                with patch.object(manager.threads_api, 'post_to_threads', return_value=True) as mock_post:
                    with patch('main.DealsFetcher') as MockFetcher:
                        mock_fetcher_instance = AsyncMock()
                        mock_fetcher_instance.fetch_all_deals = AsyncMock(return_value=sample_deals)
                        MockFetcher.return_value.__aenter__.return_value = mock_fetcher_instance

                        await manager.fetch_and_post_deals()

                        # Verify post was attempted
                        mock_post.assert_called_once()

                        # Verify deals were tracked
                        assert len(manager.posted_deals) == 2

    @pytest.mark.asyncio
    async def test_full_workflow_with_carousel_images(self, mock_env_vars):
        """Test the complete workflow with carousel post (Reddit deals with images)"""
        # Simulate Reddit deals with product images
        reddit_deals_with_images = [
            Deal(
                title="Samsung 65\" 4K TV",
                price="$499",
                original_price=None,
                discount_percentage=None,
                store="Amazon",
                link="https://amazon.com/tv",
                image_url="https://preview.redd.it/tv.jpg?auto=webp&s=abc123",
                description=None,
                score=250
            ),
            Deal(
                title="Apple AirPods Pro",
                price="$189",
                original_price=None,
                discount_percentage=None,
                store="BestBuy",
                link="https://bestbuy.com/airpods",
                image_url="https://preview.redd.it/airpods.jpg?auto=webp&s=def456",
                description=None,
                score=200
            ),
            Deal(
                title="Mechanical Keyboard RGB",
                price="$79",
                original_price=None,
                discount_percentage=None,
                store="Amazon",
                link="https://amazon.com/keyboard",
                image_url="https://b.thumbs.redditmedia.com/keyboard.jpg",
                description=None,
                score=180
            ),
            Deal(
                title="Gaming Mouse",
                price="$39",
                original_price=None,
                discount_percentage=None,
                store="Newegg",
                link="https://newegg.com/mouse",
                image_url="https://preview.redd.it/mouse.jpg?auto=webp&s=ghi789",
                description=None,
                score=150
            ),
            Deal(
                title="USB-C Cable",
                price="$12",
                original_price=None,
                discount_percentage=None,
                store="Amazon",
                link="https://amazon.com/cable",
                image_url="https://b.thumbs.redditmedia.com/cable.jpg",
                description=None,
                score=120
            )
        ]

        with patch('os.path.exists', return_value=False):
            manager = DealsPostManager()

            with patch('main.DealsFetcher') as MockFetcher:
                mock_fetcher_instance = AsyncMock()
                mock_fetcher_instance.fetch_all_deals = AsyncMock(return_value=reddit_deals_with_images)
                MockFetcher.return_value.__aenter__.return_value = mock_fetcher_instance

                # Capture the post call
                with patch.object(manager.threads_api, 'post_to_threads', return_value=True) as mock_post:
                    await manager.fetch_and_post_deals()

                    # Verify post was called
                    assert mock_post.called

                    # Get the call arguments
                    call_args = mock_post.call_args
                    post_text = call_args[0][0]
                    media_urls = call_args[1].get('media_urls')

                    # Verify post content contains deal info
                    assert "TODAY'S HOTTEST DEALS" in post_text
                    assert "Samsung 65\" 4K TV" in post_text
                    assert "$499" in post_text

                    # Verify we have 5 image URLs for carousel
                    assert media_urls is not None
                    assert len(media_urls) == 5
                    assert media_urls[0] == "https://preview.redd.it/tv.jpg?auto=webp&s=abc123"
                    assert media_urls[1] == "https://preview.redd.it/airpods.jpg?auto=webp&s=def456"
                    assert media_urls[2] == "https://b.thumbs.redditmedia.com/keyboard.jpg"
                    assert media_urls[3] == "https://preview.redd.it/mouse.jpg?auto=webp&s=ghi789"
                    assert media_urls[4] == "https://b.thumbs.redditmedia.com/cable.jpg"

                    # Verify all deals were tracked
                    assert len(manager.posted_deals) == 5

                    print("\n" + "="*60)
                    print("CAROUSEL POST TEST RESULT")
                    print("="*60)
                    print(f"\n📝 Post Content ({len(post_text)} chars):")
                    print(post_text)
                    print(f"\n📸 Image URLs ({len(media_urls)} images):")
                    for i, url in enumerate(media_urls, 1):
                        print(f"  {i}. {url}")
                    print("\n✅ This will create a CAROUSEL POST on Threads!")
                    print("="*60 + "\n")
