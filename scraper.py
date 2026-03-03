"""
Google Maps Business Lead Scraper
=================================
Scrapes business listings from Google Maps and exports to CSV.
Extracts: Name, Website, Phone Number, Address, Email.

Can be used standalone (python scraper.py) or imported by the web UI.
"""

import csv
import os
import re
import time
import random
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


# ─── Default Configuration ──────────────────────────────────────────────────

DEFAULTS = {
    'max_scrolls': 15,
    'scroll_pause': 2.0,
    'action_delay_min': 1.0,
    'action_delay_max': 2.5,
    'timeout': 8000,
    'scrape_emails': True,
    'email_timeout': 10000,
    'headless': False,
}

# Results folder
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
os.makedirs(RESULTS_DIR, exist_ok=True)


def random_delay(delay_min=1.0, delay_max=2.5):
    """Sleep for a random duration to mimic human behavior."""
    time.sleep(random.uniform(delay_min, delay_max))


def sanitize_filename(query: str) -> str:
    """Convert a search query into a safe filename."""
    name = query.lower().strip()
    name = re.sub(r'[^a-z0-9]+', '_', name)
    name = name.strip('_')
    return f"{name}.csv"


def scroll_results(page, config, progress_callback=None) -> int:
    """
    Scroll the Google Maps results panel to load all listings.
    Returns the total number of result items found.
    """
    results_selector = 'div[role="feed"]'
    max_scrolls = config.get('max_scrolls', DEFAULTS['max_scrolls'])
    scroll_pause = config.get('scroll_pause', DEFAULTS['scroll_pause'])

    try:
        page.wait_for_selector(results_selector, timeout=config.get('timeout', DEFAULTS['timeout']))
    except PlaywrightTimeout:
        if progress_callback:
            progress_callback('warning', 'Could not find results panel. Try a different search query.')
        return 0

    previous_count = 0
    no_change_count = 0
    current_count = 0

    for i in range(max_scrolls):
        page.evaluate(f'''
            const feed = document.querySelector('{results_selector}');
            if (feed) feed.scrollTop = feed.scrollHeight;
        ''')
        time.sleep(scroll_pause)

        items = page.query_selector_all(f'{results_selector} > div > div > a')
        current_count = len(items)

        if progress_callback:
            progress_callback('scroll', f'Scroll {i+1}/{max_scrolls} — {current_count} listings loaded')

        end_marker = page.query_selector('p.fontBodyMedium span:text("You\'ve reached the end of the list")')
        if end_marker:
            if progress_callback:
                progress_callback('scroll_done', f'Reached end of results ({current_count} listings)')
            break

        if current_count == previous_count:
            no_change_count += 1
            if no_change_count >= 3:
                if progress_callback:
                    progress_callback('scroll_done', f'No more results loading ({current_count} listings)')
                break
        else:
            no_change_count = 0

        previous_count = current_count
    else:
        if progress_callback:
            progress_callback('scroll_done', f'Max scrolls reached ({current_count} listings)')

    return current_count


def extract_emails_from_website(context, website_url: str, config=None) -> str:
    """
    Visit a business website and scan for email addresses.
    Checks the homepage and common contact pages.
    Returns a comma-separated string of found emails, or empty string.
    """
    if not website_url:
        return ''

    if config is None:
        config = DEFAULTS

    url = website_url.strip()
    if not url.startswith('http'):
        url = 'https://' + url

    email_pattern = re.compile(
        r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
        re.IGNORECASE
    )

    excluded_domains = {
        'sentry.io', 'wixpress.com', 'example.com', 'email.com',
        'domain.com', 'company.com', 'yoursite.com', 'website.com',
        'test.com', 'sample.com', 'placeholder.com'
    }
    excluded_patterns = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js')
    email_timeout = config.get('email_timeout', DEFAULTS['email_timeout'])

    found_emails = set()
    page = None

    try:
        page = context.new_page()
        contact_paths = ['/contact', '/contact-us', '/about', '/about-us']

        try:
            page.goto(url, wait_until='domcontentloaded', timeout=email_timeout)
            time.sleep(1.5)

            content = page.content()
            emails = email_pattern.findall(content)
            for email in emails:
                email_lower = email.lower()
                domain = email_lower.split('@')[1] if '@' in email_lower else ''
                if (domain not in excluded_domains and
                        not any(email_lower.endswith(p) for p in excluded_patterns)):
                    found_emails.add(email_lower)

            mailto_links = page.query_selector_all('a[href^="mailto:"]')
            for link in mailto_links:
                href = link.get_attribute('href') or ''
                email_match = email_pattern.search(href)
                if email_match:
                    found_emails.add(email_match.group().lower())

            if not found_emails:
                for path in contact_paths:
                    contact_url = url.rstrip('/') + path
                    try:
                        page.goto(contact_url, wait_until='domcontentloaded', timeout=email_timeout)
                        time.sleep(1)
                        content = page.content()
                        emails = email_pattern.findall(content)
                        for email in emails:
                            email_lower = email.lower()
                            domain = email_lower.split('@')[1] if '@' in email_lower else ''
                            if (domain not in excluded_domains and
                                    not any(email_lower.endswith(p) for p in excluded_patterns)):
                                found_emails.add(email_lower)

                        mailto_links = page.query_selector_all('a[href^="mailto:"]')
                        for link in mailto_links:
                            href = link.get_attribute('href') or ''
                            email_match = email_pattern.search(href)
                            if email_match:
                                found_emails.add(email_match.group().lower())

                        if found_emails:
                            break
                    except Exception:
                        continue

        except Exception:
            pass

    except Exception:
        pass
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass

    return ', '.join(sorted(found_emails))


def extract_business_details(page) -> dict:
    """
    Extract business details from the currently open listing panel.
    Returns a dict with name, address, phone, website, email.
    """
    details = {
        'name': '',
        'address': '',
        'phone': '',
        'website': '',
        'email': ''
    }

    try:
        name_el = page.query_selector('h1.DUwDvf')
        if name_el:
            details['name'] = name_el.inner_text().strip()
    except Exception:
        pass

    try:
        address_el = page.query_selector('button[data-item-id="address"] div.fontBodyMedium')
        if address_el:
            details['address'] = address_el.inner_text().strip()
        else:
            address_el = page.query_selector('button[data-item-id="address"]')
            if address_el:
                aria = address_el.get_attribute('aria-label') or ''
                details['address'] = aria.replace('Address: ', '').strip()
    except Exception:
        pass

    try:
        phone_el = page.query_selector('button[data-item-id^="phone:"] div.fontBodyMedium')
        if phone_el:
            details['phone'] = phone_el.inner_text().strip()
        else:
            phone_el = page.query_selector('button[data-item-id^="phone:"]')
            if phone_el:
                aria = phone_el.get_attribute('aria-label') or ''
                details['phone'] = aria.replace('Phone: ', '').strip()
    except Exception:
        pass

    try:
        website_el = page.query_selector('a[data-item-id="authority"] div.fontBodyMedium')
        if website_el:
            details['website'] = website_el.inner_text().strip()
        else:
            website_el = page.query_selector('a[data-item-id="authority"]')
            if website_el:
                details['website'] = website_el.get_attribute('href') or ''
    except Exception:
        pass

    return details


def scrape_google_maps(query: str, config: dict = None, progress_callback=None) -> list[dict]:
    """
    Main scraping function.
    Searches Google Maps for the query, scrolls results,
    clicks each listing, and extracts business details.

    Args:
        query: Search query string
        config: Configuration dict (uses DEFAULTS if not provided)
        progress_callback: Optional callback fn(event_type, message) for live updates
    """
    if config is None:
        config = DEFAULTS.copy()

    results = []
    seen = set()
    search_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"

    def emit(event, msg):
        if progress_callback:
            progress_callback(event, msg)
        else:
            print(f"  [{event}] {msg}")

    emit('status', f'Searching Google Maps for: "{query}"')

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=config.get('headless', DEFAULTS['headless']),
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ]
        )

        context = browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            locale='en-US',
        )

        page = context.new_page()

        emit('status', 'Opening Google Maps...')
        page.goto(search_url, wait_until='networkidle', timeout=30000)
        random_delay(config.get('action_delay_min', 1.0), config.get('action_delay_max', 2.5))

        # Handle cookie consent
        try:
            accept_btn = page.query_selector('button:has-text("Accept all")')
            if accept_btn:
                accept_btn.click()
                random_delay(config.get('action_delay_min', 1.0), config.get('action_delay_max', 2.5))
        except Exception:
            pass

        # Scroll to load results
        emit('status', 'Scrolling to load all results...')
        total_found = scroll_results(page, config, progress_callback)

        if total_found == 0:
            emit('error', 'No results found. Check your search query.')
            browser.close()
            return results

        # Collect listing links
        feed_selector = 'div[role="feed"]'
        listing_links = page.query_selector_all(f'{feed_selector} > div > div > a')
        total = len(listing_links)
        emit('status', f'Scraping details for {total} listings...')

        previous_name = ''
        for i, link in enumerate(listing_links):
            try:
                link.scroll_into_view_if_needed()
                random_delay(config.get('action_delay_min', 1.0), config.get('action_delay_max', 2.5))
                link.click()

                try:
                    page.wait_for_selector('h1.DUwDvf', timeout=config.get('timeout', DEFAULTS['timeout']))
                except PlaywrightTimeout:
                    emit('skip', f'[{i+1}/{total}] Timed out — skipping')
                    continue

                # Wait for panel to change
                for _ in range(10):
                    name_el = page.query_selector('h1.DUwDvf')
                    current_name = name_el.inner_text().strip() if name_el else ''
                    if current_name and current_name != previous_name:
                        break
                    time.sleep(0.3)

                time.sleep(0.5)

                details = extract_business_details(page)
                previous_name = details['name']

                if details['name']:
                    key = (details['name'].lower(), details['address'].lower())
                    if key in seen:
                        emit('duplicate', f'[{i+1}/{total}] {details["name"]} (duplicate, skipped)')
                        continue
                    seen.add(key)

                    results.append(details)
                    emit('business', json.dumps({
                        'index': len(results),
                        'total': total,
                        'name': details['name'],
                        'phone': details['phone'],
                        'website': details['website'],
                        'address': details['address'],
                    }))

            except Exception as e:
                emit('error', f'[{i+1}/{total}] Error: {e}')
                continue

        # Phase 2: Email scraping
        if config.get('scrape_emails', DEFAULTS['scrape_emails']):
            businesses_with_sites = [r for r in results if r.get('website')]
            if businesses_with_sites:
                emit('status', f'Scanning {len(businesses_with_sites)} websites for email addresses...')
                for i, biz in enumerate(businesses_with_sites):
                    emit('email_check', json.dumps({
                        'index': i + 1,
                        'total': len(businesses_with_sites),
                        'website': biz['website']
                    }))
                    email = extract_emails_from_website(context, biz['website'], config)
                    biz['email'] = email
                    if email:
                        emit('email_found', json.dumps({
                            'name': biz['name'],
                            'email': email
                        }))
                    random_delay(config.get('action_delay_min', 1.0), config.get('action_delay_max', 2.5))

        browser.close()

    return results


def save_to_csv(results: list[dict], filename: str) -> str:
    """Save scraped results to a CSV file in the results/ folder."""
    filepath = os.path.join(RESULTS_DIR, filename)

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'address', 'phone', 'website', 'email'])
        writer.writeheader()
        writer.writerows(results)

    return filepath


# ─── CLI Mode ────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Google Maps Business Lead Scraper")
    print("=" * 60)

    query = input("\n  Enter search query (e.g. 'plumbers in Dallas TX'): ").strip()

    if not query:
        print("  ✗ No query entered. Exiting.")
        return

    def cli_progress(event, msg):
        if event == 'business':
            data = json.loads(msg)
            print(f"  [{data['index']}/{data['total']}] ✓ {data['name']}")
            if data.get('phone'):
                print(f"           📞 {data['phone']}")
            if data.get('website'):
                print(f"           🌐 {data['website']}")
            if data.get('address'):
                print(f"           📍 {data['address']}")
        elif event == 'email_found':
            data = json.loads(msg)
            print(f"           📧 {data['email']}")
        elif event == 'email_check':
            data = json.loads(msg)
            print(f"  [{data['index']}/{data['total']}] Checking {data['website']}...", end=' ')
        elif event in ('status', 'scroll_done', 'warning', 'error'):
            print(f"  {msg}")
        elif event == 'scroll':
            print(f"  {msg}", end='\r')

    results = scrape_google_maps(query, progress_callback=cli_progress)

    if not results:
        print("\n  ✗ No results scraped.")
        return

    filename = sanitize_filename(query)
    filepath = save_to_csv(results, filename)

    emails_found = sum(1 for r in results if r.get('email'))
    print("\n" + "=" * 60)
    print(f"  ✓ Done! Scraped {len(results)} businesses")
    print(f"  📧 Emails found: {emails_found}/{len(results)}")
    print(f"  📄 Saved to: {filepath}")
    print("=" * 60)


if __name__ == '__main__':
    main()
