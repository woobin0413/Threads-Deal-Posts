# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an automated deals aggregator that fetches deals from free APIs and web scraping sources, then posts them to Threads (Meta's platform). It's designed to run as a scheduled task via cron or Windows Task Scheduler.

## Running the Application

### Development Environment
Always use the virtual environment for running scripts:
```bash
source venv/bin/activate && python main.py
```

### Running Tests
```bash
source venv/bin/activate && pytest test_main.py -v
```

Run specific test class:
```bash
source venv/bin/activate && pytest test_main.py::TestDealsFetcher -v
```

Run with coverage:
```bash
source venv/bin/activate && pytest test_main.py --cov=main
```

### Installing Dependencies
```bash
source venv/bin/activate && pip install -r requirements.txt
```

## Architecture

### Core Components

**Deal Flow**: Reddit/CheapShark/Slickdeals → DealsFetcher → DealsPostManager → ThreadsAPI → Threads Platform

1. **DealsFetcher** (async context manager)
   - Uses aiohttp for concurrent HTTP requests to multiple sources
   - Implements async methods for each deal source
   - Handles deduplication based on normalized title matching
   - Scores and ranks deals by popularity/rating
   - Sources: Reddit JSON API (free), CheapShark API (free), Slickdeals (web scraping)

2. **ThreadsAPI**
   - Two-step posting process: create media container → publish container
   - Requires THREADS_ACCESS_TOKEN and THREADS_USER_ID from .env
   - Implements rate limit checking (250 posts per 24 hours)
   - 1-second delay between container creation and publishing

3. **DealsPostManager**
   - Orchestrates the entire fetch-and-post workflow
   - Maintains posted_deals.json to prevent duplicate posts (keeps last 100)
   - Formats deals with emoji rankings (🥇🥈🥉4️⃣5️⃣)
   - Enforces 500 character limit for Threads posts
   - Selects top 5 deals by score for each post

### Async Architecture
- aiohttp is used for concurrent fetching from multiple sources (3+ seconds vs 9+ seconds sequential)
- All deal sources are fetched in parallel via asyncio.gather()
- DealsFetcher uses async context manager pattern for proper session lifecycle

### Data Flow
1. Main entry point checks for required env vars (THREADS_ACCESS_TOKEN, THREADS_USER_ID)
2. DealsPostManager.fetch_and_post_deals() runs async workflow
3. DealsFetcher fetches from all enabled sources concurrently
4. Deals are scored, sorted, deduplicated
5. Previously posted deals filtered out using posted_deals.json
6. Top 5 new deals formatted into post content
7. ThreadsAPI posts to Threads (container → publish)
8. Posted deal IDs saved to prevent future duplicates

## Environment Variables

Required in `.env` file:
- `THREADS_ACCESS_TOKEN`: Long-lived (60-day) Threads API token
- `THREADS_USER_ID`: Numeric Threads user ID

Optional:
- `USE_DUMMY_DATA=true`: Enables DummyJSON API for testing

## Key Implementation Details

### Deal Sources
- **Reddit**: Uses public JSON API (no auth) at reddit.com/r/deals/hot.json
  - Filters out promoted/sponsored posts to capture only human-posted deals
  - Checks both `promoted` and `is_sponsored` fields in post data
  - Extracts product images from preview images or thumbnails
  - Images are automatically included in carousel posts
  - Only deal source currently in use

### Duplicate Detection
- Title-based: Normalized to alphanumeric only, first 50 chars
- Store+Title ID tracked in posted_deals.json
- Two-layer deduplication: within-fetch and across-runs

### Threads API Specifics
- Media container must be created before publishing
- Text posts use media_type='TEXT'
- Single image posts use media_type='IMAGE' with image_url parameter
- Carousel posts use media_type='CAROUSEL' with multiple image containers
  - Supports up to 20 images per carousel
  - Creates individual media containers for each image
  - Combines them into a carousel container with text caption
  - Automatically used when 2+ deals have images
- Rate limits: 250 posts/24hrs, 60 requests/min, 1 post/second

### Post Formatting
- Header: "🔥 TODAY'S HOTTEST DEALS 🔥" with date
- Each deal: emoji rank + title + price + discount + store + link
- Footer: hashtags (#deals #savings #shopping #discounts)
- Auto-truncation at 500 chars (Threads limit)
- Images: Automatically creates carousel with product images when available
  - Falls back to text-only if no images found

## Common Development Tasks

### Adding a New Deal Source
1. Add async method to DealsFetcher class following pattern: `async def fetch_SOURCE_deals(self) -> List[Deal]`
2. Parse API/HTML response into Deal objects with score
3. Filter out promoted/sponsored content if applicable
4. Add method call to `fetch_all_deals()` tasks list
5. Add logger.info statement for fetch count
6. Handle exceptions gracefully (return empty list on error)

### Modifying Post Format
- `format_deal_text()`: Individual deal formatting (main.py:458-482)
- `create_post_content()`: Overall post structure (main.py:484-508)
- Emoji rankings defined in emoji_map (main.py:460-467)

### Testing Modifications
- All tests use pytest with asyncio support
- Mock environment variables via `mock_env_vars` fixture
- Mock aiohttp responses using AsyncMock
- Test files follow pattern: Test{ClassName} with test_{method}_success/error

## Logging
- Logs to both `deals_poster.log` file and console
- Format: timestamp - module - level - message
- Key events logged: fetch counts, API responses, errors, post success/failure

## Scheduled Execution
The main() function is designed for one-shot execution (fetch → post → exit). Schedule via:
- **macOS/Linux**: cron (e.g., "0 9,18 * * *" for 9 AM and 6 PM daily)
- **Windows**: Task Scheduler with Python interpreter and main.py as arguments
- Always use absolute paths in scheduler and activate venv before running

## Error Handling
- API errors return empty lists to allow partial success
- Missing env vars cause early exit with error code 1
- Threads API errors logged with full response text
- KeyboardInterrupt handled gracefully
