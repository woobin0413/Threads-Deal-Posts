"""
Scrape deals from Slickdeals with at least 100 thumbs up
"""

import requests
from bs4 import BeautifulSoup
import json
from typing import List, Dict

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

def scrape_slickdeals(min_thumbs_up: int = 100, max_deals: int = 5) -> List[Dict]:
    """
    Scrape deals from Slickdeals frontpage with minimum thumbs up

    Args:
        min_thumbs_up: Minimum number of thumbs up required
        max_deals: Maximum number of deals to return

    Returns:
        List of deal dictionaries
    """
    url = "https://slickdeals.net/"

    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    print("=" * 70)
    print("🔍 Scraping Slickdeals.net")
    print("=" * 70)
    print(f"URL: {url}")
    print(f"Min Thumbs Up: {min_thumbs_up}")
    print(f"Max Deals: {max_deals}")
    print("-" * 70)

    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")

        if response.status_code != 200:
            print(f"❌ Failed to fetch page")
            return []

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all deal cards
        # Slickdeals uses various class names, let's try multiple selectors
        deal_cards = soup.find_all('div', class_='dealCard') or \
                     soup.find_all('li', class_='fpGridBox') or \
                     soup.find_all('div', attrs={'data-role': 'dealCard'})

        print(f"Found {len(deal_cards)} deal cards")

        if not deal_cards:
            print("⚠️  No deal cards found. Page structure may have changed.")
            print("\nDebugging - Looking for common patterns:")

            # Debug: find any divs with 'deal' in class name
            potential_deals = soup.find_all('div', class_=lambda x: x and 'deal' in x.lower())
            print(f"   Found {len(potential_deals)} elements with 'deal' in class")

            # Debug: find list items
            list_items = soup.find_all('li')
            print(f"   Found {len(list_items)} list items")

            # Try to find any vote/thumb elements
            vote_elements = soup.find_all(class_=lambda x: x and ('vote' in str(x).lower() or 'thumb' in str(x).lower()))
            print(f"   Found {len(vote_elements)} vote/thumb elements")

            return []

        deals = []

        for card in deal_cards:
            try:
                # Extract title - it's in the second <a> tag
                links = card.find_all('a')
                if len(links) < 2:
                    continue

                title_elem = links[1]  # Second link has the title
                title = title_elem.get_text(strip=True)
                link = title_elem.get('href', '')

                # Make link absolute if relative
                if link and not link.startswith('http'):
                    link = f"https://slickdeals.net{link}"

                # Extract thumbs up count - class: dealCardSocialControls__voteCount
                thumbs_elem = card.find('span', class_='dealCardSocialControls__voteCount')

                thumbs_up = 0
                if thumbs_elem:
                    thumbs_text = thumbs_elem.get_text(strip=True)
                    # Extract number from text like "+123" or "123"
                    import re
                    match = re.search(r'\d+', thumbs_text)
                    if match:
                        thumbs_up = int(match.group())

                # Skip if below threshold
                if thumbs_up < min_thumbs_up:
                    continue

                # Extract price - class: dealCard__price
                price_elem = card.find('span', class_='dealCard__price')
                price = price_elem.get_text(strip=True) if price_elem else "See Deal"

                # Extract original price if available
                original_price_elem = card.find('span', class_='dealCard__originalPrice')
                original_price = original_price_elem.get_text(strip=True) if original_price_elem else None

                # Extract store - from data-store-id or find store name in card
                store = "Various"
                # Try to find store name in the card text
                store_elem = card.find('a', class_=lambda x: x and 'merchant' in str(x).lower())
                if store_elem:
                    store = store_elem.get_text(strip=True)

                # Extract image - look for product images, not avatars
                img_elems = card.find_all('img')
                image_url = None
                for img in img_elems:
                    src = img.get('src') or img.get('data-src')
                    # Skip avatar images
                    if src and 'avatar' not in src.lower():
                        image_url = src
                        if not image_url.startswith('http'):
                            image_url = f"https:{image_url}" if image_url.startswith('//') else f"https://slickdeals.net{image_url}"
                        break

                # Extract description if available
                desc_elem = card.find('div', class_='itemDesc') or \
                           card.find('p', class_='description')

                description = desc_elem.get_text(strip=True) if desc_elem else None

                deal = {
                    'title': title,
                    'price': price,
                    'original_price': original_price,
                    'store': store,
                    'link': link,
                    'thumbs_up': thumbs_up,
                    'image_url': image_url,
                    'description': description
                }

                deals.append(deal)

                if len(deals) >= max_deals:
                    break

            except Exception as e:
                print(f"⚠️  Error parsing deal card: {e}")
                continue

        print(f"\n✅ Successfully scraped {len(deals)} deals with {min_thumbs_up}+ thumbs up")
        return deals[:max_deals]

    except Exception as e:
        print(f"❌ Error scraping Slickdeals: {e}")
        return []


if __name__ == "__main__":
    # Test the scraper
    deals = scrape_slickdeals(min_thumbs_up=100, max_deals=5)

    print("\n" + "=" * 70)
    print(f"📊 RESULTS: {len(deals)} Deals Found")
    print("=" * 70)

    for i, deal in enumerate(deals, 1):
        print(f"\n🔹 Deal #{i}")
        print(f"   Title: {deal['title']}")
        print(f"   Price: {deal['price']}")
        print(f"   Store: {deal['store']}")
        print(f"   Thumbs Up: {deal['thumbs_up']} 👍")
        print(f"   Link: {deal['link']}")
        if deal['image_url']:
            print(f"   Image: {deal['image_url'][:60]}...")
        if deal['description']:
            desc_preview = deal['description'][:100] + '...' if len(deal['description']) > 100 else deal['description']
            print(f"   Description: {desc_preview}")

    # Save to JSON
    if deals:
        with open('slickdeals_output.json', 'w', encoding='utf-8') as f:
            json.dump(deals, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Saved deals to: slickdeals_output.json")

    print("\n" + "=" * 70)
