"""
Send Amazon deals from Slickdeals to your email
Fetches deals with 60+ thumbs up from Slickdeals, Amazon only
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import re

load_dotenv()

# ============= CONFIGURATION =============
RECIPIENT_EMAILS = os.getenv('RECIPIENT_EMAILS', '').split(',')
RECIPIENT_EMAILS = [email.strip() for email in RECIPIENT_EMAILS if email.strip()]

if not RECIPIENT_EMAILS:
    print("❌ Error: RECIPIENT_EMAILS not configured in .env file")
    exit(1)

MIN_THUMBS_UP = 60
MAX_DEALS = 10
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


def scrape_slickdeals_amazon(min_thumbs_up: int = 60, max_deals: int = 10):
    """Scrape Amazon deals from Slickdeals"""

    # Try multiple pages to find enough deals
    urls = [
        "https://slickdeals.net/",
        "https://slickdeals.net/?page=2",
        "https://slickdeals.net/?page=3"
    ]

    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    all_deals = []

    print(f"🔍 Scraping Slickdeals for Amazon deals with {min_thumbs_up}+ thumbs up...")

    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.content, 'html.parser')

            # Find all deal cards
            deal_cards = soup.find_all('div', class_='dealCard') or \
                        soup.find_all('li', class_='fpGridBox') or \
                        soup.find_all('div', attrs={'data-role': 'dealCard'})

            print(f"   Found {len(deal_cards)} deal cards on {url}")

            for card in deal_cards:
                try:
                    # Extract link first to check if it's Amazon
                    links = card.find_all('a')
                    if len(links) < 2:
                        continue

                    title_elem = links[1]
                    title = title_elem.get_text(strip=True)
                    link = title_elem.get('href', '')

                    if link and not link.startswith('http'):
                        link = f"https://slickdeals.net{link}"

                    # Check if deal links to Amazon
                    is_amazon = False

                    # Check store name
                    store_elem = card.find('a', class_=lambda x: x and 'merchant' in str(x).lower())
                    if store_elem and 'amazon' in store_elem.get_text(strip=True).lower():
                        is_amazon = True

                    # Check if title or link mentions Amazon
                    if 'amazon' in title.lower() or 'amazon' in link.lower():
                        is_amazon = True

                    # Skip non-Amazon deals
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

                    deal = {
                        'title': title,
                        'price': price,
                        'original_price': original_price,
                        'link': link,
                        'thumbs_up': thumbs_up,
                        'image_url': image_url
                    }

                    all_deals.append(deal)
                    print(f"   ✓ Found: {title[:60]}... (👍 {thumbs_up})")

                    if len(all_deals) >= max_deals:
                        break

                except Exception as e:
                    continue

            if len(all_deals) >= max_deals:
                break

        except Exception as e:
            print(f"   ⚠️  Error scraping {url}: {e}")
            continue

    # Sort by thumbs up descending
    all_deals.sort(key=lambda x: x['thumbs_up'], reverse=True)

    print(f"\n✅ Found {len(all_deals)} Amazon deals with {min_thumbs_up}+ thumbs up")
    return all_deals[:max_deals]


def format_deals_for_email(deals: list, max_deals: int = 10) -> tuple:
    """Format deals list into HTML email"""
    if not deals:
        return "No Amazon Deals Today", "<p>No Amazon deals found from Slickdeals with 60+ thumbs up.</p>"

    subject = f"🔥 {len(deals)} Hot Amazon Deals from Slickdeals"

    html = """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }
            .header { background: linear-gradient(135deg, #FF9900 0%, #FF6600 100%); color: white; padding: 20px; text-align: center; border-radius: 10px; }
            .deal { background: #f8f9fa; border-left: 4px solid #FF9900; padding: 15px; margin: 15px 0; border-radius: 5px; }
            .deal-title { font-size: 18px; font-weight: bold; color: #333; margin-bottom: 10px; }
            .deal-price { font-size: 24px; color: #28a745; font-weight: bold; }
            .deal-original { font-size: 16px; color: #999; text-decoration: line-through; }
            .deal-link { display: inline-block; background: #FF9900; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 10px; }
            .deal-link:hover { background: #FF6600; }
            .deal-meta { color: #666; font-size: 14px; margin-top: 10px; }
            .footer { text-align: center; color: #999; margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔥 Amazon Deals from Slickdeals</h1>
            <p>Top Amazon deals with 60+ thumbs up</p>
        </div>
    """

    for i, deal in enumerate(deals[:max_deals], 1):
        title = deal['title']
        price = deal.get('price', 'See Deal')
        original = deal.get('original_price')
        thumbs = deal.get('thumbs_up', 0)
        link = deal.get('link', '')
        image = deal.get('image_url', '')

        html += f"""
        <div class="deal">
            <div class="deal-title">{i}. {title}</div>
            """

        if image:
            html += f'<img src="{image}" style="max-width: 100%; height: auto; border-radius: 5px; margin: 10px 0;" />'

        html += f"""
            <div>
                <span class="deal-price">{price}</span>
                """

        if original:
            html += f'<span class="deal-original">{original}</span>'
            try:
                price_num = float(price.replace('$', '').replace(',', ''))
                orig_num = float(original.replace('$', '').replace(',', ''))
                discount = int((1 - price_num/orig_num) * 100)
                html += f' <span style="color: #dc3545; font-weight: bold;">({discount}% OFF)</span>'
            except:
                pass

        html += f"""
            </div>
            <div class="deal-meta">
                👍 {thumbs} thumbs up on Slickdeals
            </div>
            <a href="{link}" class="deal-link">View Deal on Slickdeals →</a>
        </div>
        """

    html += """
        <div class="footer">
            <p>Powered by Slickdeals</p>
            <p style="font-size: 12px;">You can unsubscribe by stopping the script.</p>
        </div>
    </body>
    </html>
    """

    return subject, html


def send_email(subject: str, html_body: str, recipient: str) -> bool:
    """Send HTML email via Gmail"""
    sender_email = os.getenv('SENDER_EMAIL')
    sender_password = os.getenv('SENDER_EMAIL_PASSWORD')

    if not sender_email or not sender_password:
        print("❌ Missing email credentials in .env file")
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = recipient

        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(sender_email, sender_password)
            smtp.send_message(msg)

        print(f"✅ Email sent to {recipient}")
        return True

    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False


def main():
    print("=" * 70)
    print("📧 Fetching Amazon Deals from Slickdeals and Sending to Email")
    print("=" * 70)

    # Fetch deals
    deals = scrape_slickdeals_amazon(min_thumbs_up=MIN_THUMBS_UP, max_deals=MAX_DEALS)

    if not deals:
        print("\n⚠️  No Amazon deals found with 60+ thumbs up")
        print("   Sending email anyway to notify...")

    # Format email
    subject, html_body = format_deals_for_email(deals, max_deals=MAX_DEALS)
    print(f"\n📧 Email Subject: {subject}")

    # Send to all recipients
    print(f"\n📤 Sending to {len(RECIPIENT_EMAILS)} recipients...")

    all_success = True
    for recipient in RECIPIENT_EMAILS:
        print(f"   Sending to {recipient}...")
        success = send_email(subject, html_body, recipient)
        if not success:
            all_success = False

    if all_success:
        print("\n✅ Done! Check your email!")
    else:
        print("\n⚠️  Some emails failed to send.")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
