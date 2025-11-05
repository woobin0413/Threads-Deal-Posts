# Deals to Threads Auto-Poster 🛍️

An automated Python application that fetches the best deals from FREE APIs and web scraping, then posts them to Threads. Designed to run via Windows Task Scheduler or cron job.

## Key Features 🚀

- **FREE API Integration**:
  - **CheapShark API**: Gaming deals from Steam, Epic, GOG (NO AUTH REQUIRED!)
  - **Reddit JSON API**: Hot deals from r/deals (NO AUTH REQUIRED!)
  - More free APIs can be easily added

- **Web Scraping Fallback**:
  - Slickdeals front page deals
  - BeautifulSoup for HTML parsing

- **Async Performance with aiohttp**:
  - Fetches from multiple sources concurrently
  - Much faster than sequential requests
  - All sources fetched in parallel

- **Smart Deal Selection**:
  - Scores and ranks deals by popularity
  - Removes duplicates automatically
  - Tracks posted deals to avoid repetition
  - Selects top 5 deals for each post

- **Professional Formatting**:
  - Eye-catching emojis and separators
  - Structured deal information
  - Automatic hashtag inclusion
  - Character limit compliance (500 chars)

## Why aiohttp? 🔄

**aiohttp** is used for asynchronous HTTP requests. Here's why it's important:

1. **Concurrent Fetching**: Instead of waiting for each API/website one by one, aiohttp fetches all sources simultaneously
2. **Speed**: What would take 10 seconds sequentially takes 2-3 seconds with async
3. **Efficiency**: Single thread handles multiple I/O operations
4. **Scalability**: Easy to add more sources without slowing down

Example: If fetching from 3 sources takes 3 seconds each:
- Sequential (regular requests): 9 seconds total
- Async (aiohttp): 3 seconds total (all parallel)

## Free APIs Used 🆓

### CheapShark API (Gaming Deals)
- **URL**: https://www.cheapshark.com/api/1.0/deals
- **Auth**: NONE REQUIRED!
- **Provides**: PC game deals from Steam, Epic Games, GOG, etc.
- **Documentation**: https://apidocs.cheapshark.com/

### Reddit JSON API
- **URL**: https://www.reddit.com/r/deals/hot.json
- **Auth**: NONE REQUIRED!
- **Provides**: Community-voted deals
- **Note**: Just add .json to any Reddit URL

### Other Free Deal APIs You Can Add:
- **FakeStoreAPI**: https://fakestoreapi.com (test data)
- **DummyJSON**: https://dummyjson.com (sample products)
- **Best Buy API**: Requires free key from developer.bestbuy.com
- **Walmart API**: Requires free key from developer.walmart.com

## Prerequisites 📋

1. **Python 3.8+** installed on your system
2. **IntelliJ IDEA** with Python plugin (or PyCharm)
3. **Meta Developer Account** with Threads API access
4. **Threads Business Account** (verified)

## Setup Instructions 🔧

### 1. Meta/Threads API Setup

1. **Create a Meta Developer Account**:
   - Go to [developers.facebook.com](https://developers.facebook.com)
   - Sign up or log in with your Facebook account

2. **Create a New App**:
   - In the dashboard, click "Create App"
   - Select "Business" as the app type
   - Choose "Access the Threads API" as the use case
   - Fill in the app details

3. **Configure App Permissions**:
   - Add these permissions:
     - `threads_basic`
     - `threads_content_publish`
     - `threads_manage_insights` (optional, for analytics)

4. **Set OAuth Redirect URL**:
   - Add redirect URL: `https://oauth.pstmn.io/v1/callback` (for Postman)
   - Or your own callback URL if you have a web server

5. **Get Your Credentials**:
   - Find your **App ID** and **App Secret** in App Settings > Basic
   - Keep these secure!

6. **Generate Access Token**:
   ```
   Step 1: Get Authorization Code
   https://threads.net/oauth/authorize?
     client_id=YOUR_CLIENT_ID&
     redirect_uri=YOUR_REDIRECT_URI&
     scope=threads_basic,threads_content_publish&
     response_type=code

   Step 2: Exchange for Short-Lived Token
   POST https://graph.threads.net/oauth/access_token
   Body: {
     client_id: YOUR_CLIENT_ID,
     client_secret: YOUR_CLIENT_SECRET,
     grant_type: authorization_code,
     redirect_uri: YOUR_REDIRECT_URI,
     code: AUTHORIZATION_CODE
   }

   Step 3: Exchange for Long-Lived Token (60 days)
   GET https://graph.threads.net/access_token?
     grant_type=th_exchange_token&
     client_secret=YOUR_CLIENT_SECRET&
     access_token=SHORT_LIVED_TOKEN
   ```

7. **Get Your Threads User ID**:
   ```
   GET https://graph.threads.net/v1.0/me?
     fields=id,username&
     access_token=YOUR_ACCESS_TOKEN
   ```

### 2. Project Setup in IntelliJ

1. **Clone/Create Project**:
   ```bash
   # Create project directory
   mkdir threads-deals-poster
   cd threads-deals-poster
   
   # Copy the provided files
   # - deals_to_threads.py
   # - requirements.txt
   # - .env.template
   ```

2. **Open in IntelliJ**:
   - Open IntelliJ IDEA
   - File > Open > Select project directory
   - Configure Python interpreter (File > Project Structure)

3. **Create Virtual Environment**:
   ```bash
   python -m venv venv
   
   # Activate virtual environment
   # Windows:
   venv\Scripts\activate
   # Mac/Linux:
   source venv/bin/activate
   ```

4. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure Environment Variables**:
   ```bash
   # Copy template
   cp .env.template .env
   
   # Edit .env file with your credentials
   THREADS_USER_ID=your_numeric_user_id
   THREADS_ACCESS_TOKEN=your_long_lived_token
   ```

### 3. IntelliJ Run Configuration

1. **Create Run Configuration**:
   - Run > Edit Configurations
   - Click + > Python
   - Name: "Deals Poster"
   - Script path: Select `deals_to_threads.py`
   - Environment variables: Load from .env file
   - Python interpreter: Select your venv interpreter

2. **Optional: Create Debug Configuration**:
   - Duplicate the run configuration
   - Name it "Deals Poster (Debug)"
   - Add program arguments: `--debug` (if you implement debug mode)

## Usage 🎯

### Running the Application

1. **Manual Test Run**:
   ```bash
   python deals_to_threads.py
   ```
   This will fetch deals and post immediately, then exit.

2. **Windows Task Scheduler Setup** (Recommended):

   a. **Open Task Scheduler**:
   - Press `Win + R`, type `taskschd.msc`, press Enter

   b. **Create New Task**:
   - Click "Create Basic Task" in Actions panel
   - Name: "Threads Deals Poster"
   - Description: "Posts deals to Threads twice daily"

   c. **Set Trigger**:
   - Choose "Daily"
   - Start time: Set your first post time (e.g., 9:00 AM)
   - Recur every: 1 day

   d. **Set Action**:
   - Action: "Start a program"
   - Program/script: `C:\Python39\python.exe` (your Python path)
   - Arguments: `deals_to_threads.py`
   - Start in: `C:\path\to\your\project` (project directory)

   e. **Create Second Task for Evening**:
   - Repeat above steps
   - Set trigger time to 6:00 PM

   f. **Additional Settings**:
   - Check "Run whether user is logged on or not"
   - Check "Run with highest privileges"
   - Under Conditions: Uncheck "Start only on AC power"

3. **Linux/Mac Cron Setup**:
   ```bash
   # Edit crontab
   crontab -e
   
   # Add these lines (adjust paths):
   0 9 * * * cd /path/to/project && /usr/bin/python3 deals_to_threads.py
   0 18 * * * cd /path/to/project && /usr/bin/python3 deals_to_threads.py
   ```

4. **Check Logs**:
   - Logs are saved to `deals_poster.log`
   - Check for successful posts or errors

### Customization Options

1. **Add More FREE APIs**:
   ```python
   # In DealsFetcher class, add a new method:
   async def fetch_fakestore_deals(self) -> List[Deal]:
       url = "https://fakestoreapi.com/products?limit=10"
       async with self.session.get(url) as response:
           # Parse and return deals
   ```

2. **Adjust Number of Deals**:
   ```python
   # In create_post_content(), change:
   for i, deal in enumerate(deals[:5], 1):  # Change 5 to desired number
   ```

3. **Add More Deal Sources**:
   - Create new method in `DealsFetcher` class
   - Add to `fetch_all_deals()` tasks list
   - No authentication complexity!

4. **Modify Post Format**:
   - Edit `format_deal_text()` for individual deals
   - Edit `create_post_content()` for overall structure

5. **Enable Test Data**:
   ```bash
   # In .env file, add:
   USE_DUMMY_DATA=true  # Enables DummyJSON API for testing
   ```

## API Rate Limits ⚠️

Threads API has the following limits:
- **250 API posts** per 24-hour period per profile
- **60 requests** per minute for most endpoints
- **1 request** per second for publishing

The application handles these automatically, but be aware when testing.

## Troubleshooting 🔍

### Common Issues and Solutions

1. **Authentication Error**:
   - Verify your access token is valid
   - Check token hasn't expired (60 days for long-lived)
   - Ensure User ID matches the token

2. **No Deals Fetched**:
   - Check internet connection
   - Verify deal source websites are accessible
   - Review logs for specific errors
   - Some sources may block frequent requests

3. **Rate Limit Errors**:
   - Check current limits: `threads_api.check_rate_limits()`
   - Reduce posting frequency
   - Wait for limit reset (usually 24 hours)

4. **Character Limit Issues**:
   - Posts are auto-truncated to 500 chars
   - Reduce number of deals or description length

5. **Module Import Errors**:
   - Ensure virtual environment is activated
   - Reinstall requirements: `pip install -r requirements.txt`

## Advanced Features 🔮

### Planned Enhancements

1. **Amazon API Integration**:
   ```python
   # Add to DealsFetcher class
   async def fetch_amazon_deals(self):
       # Use Amazon Product Advertising API
       pass
   ```

2. **URL Shortener Integration**:
   ```python
   # Add URL shortening for cleaner posts
   import pyshorteners
   shortener = pyshorteners.Shortener()
   short_url = shortener.tinyurl.short(deal.link)
   ```

3. **Deal Categories**:
   - Electronics-focused posts
   - Fashion deals
   - Home & Garden
   - Rotating categories by day

4. **Analytics Tracking**:
   ```python
   # Track post performance
   def get_post_insights(post_id):
       endpoint = f"{api_base}/{post_id}/insights"
       # Fetch likes, comments, shares
   ```

5. **Image Support**:
   - Download deal images
   - Create image collages
   - Post as media with captions

## Project Structure 📁

```
threads-deals-poster/
├── deals_to_threads.py      # Main application
├── requirements.txt         # Python dependencies
├── .env                    # Your credentials (git-ignored)
├── .env.template           # Template for env vars
├── README.md               # This file
├── deals_poster.log        # Application logs
├── posted_deals.json       # Tracking posted deals
└── venv/                   # Virtual environment
```

## Security Best Practices 🔐

1. **Never commit `.env` file** to version control
2. **Rotate access tokens** periodically
3. **Use long-lived tokens** for production
4. **Store credentials securely** (consider using secret management)
5. **Monitor API usage** for unusual activity

## Contributing 🤝

Feel free to extend this project with:
- Additional deal sources
- Better deal scoring algorithms
- Image generation for posts
- Multi-platform posting (Twitter/X, Facebook, etc.)
- Web dashboard for monitoring

## Support 💬

For issues with:
- **Threads API**: Check [Meta Developer Docs](https://developers.facebook.com/docs/threads)
- **Python/Code**: Review logs and error messages
- **Deal Sources**: Verify website accessibility

## License 📄

This project is provided as-is for educational purposes. Ensure you comply with:
- Threads API Terms of Service
- Deal source websites' Terms of Service
- Applicable data protection regulations

---

**Happy Posting! 🚀** Follow your Threads account to see the deals in action!
