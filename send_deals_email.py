"""
Send Slickdeals to your email (much more reliable than SMS!)
Uses Gmail SMTP - 100% FREE, no limitations
"""

from scrape_slickdeals import scrape_slickdeals
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

# ============= CONFIGURATION =============
# Get recipient emails from .env (comma-separated)
RECIPIENT_EMAILS = os.getenv('RECIPIENT_EMAILS', '').split(',')
RECIPIENT_EMAILS = [email.strip() for email in RECIPIENT_EMAILS if email.strip()]

if not RECIPIENT_EMAILS:
    print("❌ Error: RECIPIENT_EMAILS not configured in .env file")
    print("   Add: RECIPIENT_EMAILS=email1@example.com,email2@example.com")
    exit(1)

# Scraping settings
MIN_THUMBS_UP = 50  # Minimum thumbs up for deals
MAX_DEALS = 5       # Maximum number of deals to include


def format_deals_for_email(deals: list, max_deals: int = 5) -> tuple:
    """
    Format deals list into HTML email

    Returns:
        tuple: (subject, html_body)
    """
    if not deals:
        return "No Deals Today", "<p>No deals found matching criteria.</p>"

    # Create subject
    subject = f"🔥 {len(deals[:max_deals])} Hot Deals on Slickdeals"

    # Create HTML body
    html = """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }
            .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; border-radius: 10px; }
            .deal { background: #f8f9fa; border-left: 4px solid #667eea; padding: 15px; margin: 15px 0; border-radius: 5px; }
            .deal-title { font-size: 18px; font-weight: bold; color: #333; margin-bottom: 10px; }
            .deal-price { font-size: 24px; color: #28a745; font-weight: bold; }
            .deal-original { font-size: 16px; color: #999; text-decoration: line-through; }
            .deal-link { display: inline-block; background: #667eea; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 10px; }
            .deal-link:hover { background: #764ba2; }
            .deal-meta { color: #666; font-size: 14px; margin-top: 10px; }
            .footer { text-align: center; color: #999; margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔥 Today's Hot Deals</h1>
            <p>Top deals from Slickdeals with 50+ likes</p>
        </div>
    """

    for i, deal in enumerate(deals[:max_deals], 1):
        title = deal['title']
        price = deal.get('price', 'N/A')
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
            # Calculate discount percentage
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
                👍 {thumbs} likes
            </div>
            <a href="{link}" class="deal-link">View Deal →</a>
        </div>
        """

    html += """
        <div class="footer">
            <p>Powered by Slickdeals Scraper</p>
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
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = recipient

        # Attach HTML body
        msg.attach(MIMEText(html_body, 'html'))

        # Send via Gmail SMTP
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(sender_email, sender_password)
            smtp.send_message(msg)

        print(f"✅ Email sent to {recipient}")
        return True

    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False


# ============= MAIN =============
if __name__ == "__main__":
    print("=" * 70)
    print("📧 Scraping Slickdeals and Sending to Your Email")
    print("=" * 70)

    # Step 1: Scrape deals
    print(f"\n🔍 Fetching deals with {MIN_THUMBS_UP}+ thumbs up...")
    deals = scrape_slickdeals(min_thumbs_up=MIN_THUMBS_UP, max_deals=MAX_DEALS)

    if not deals:
        print("❌ No deals found matching criteria")
        exit(1)

    print(f"✅ Found {len(deals)} deals!")

    # Step 2: Format for email
    subject, html_body = format_deals_for_email(deals, max_deals=MAX_DEALS)

    print(f"\n📧 Email Subject: {subject}")

    # Step 3: Send email to all recipients
    print(f"\n📤 Sending to {len(RECIPIENT_EMAILS)} recipients...")

    all_success = True
    for recipient in RECIPIENT_EMAILS:
        print(f"   Sending to {recipient}...")
        success = send_email(subject, html_body, recipient)
        if not success:
            all_success = False

    if all_success:
        print("\n✅ Done! Check your email for the deals!")
        print(f"   Look for: {subject}")
    else:
        print("\n⚠️  Some emails failed to send. Check your .env configuration.")

    print("\n" + "=" * 70)
