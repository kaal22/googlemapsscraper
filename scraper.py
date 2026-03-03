"""
Google Maps Business Lead Scraper
=================================
Scrapes business listings from Google Maps and exports to CSV.
Extracts: Name, Website, Phone Number, Address.

Usage:
    python scraper.py
    → Enter a search query when prompted (e.g. "plumbers in Dallas TX")
"""

import csv
import os
import re
import time
import random
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


# ─── Configuration ───────────────────────────────────────────────────────────

MAX_SCROLLS = 15            # Max scroll attempts to load more results
SCROLL_PAUSE = 2.0          # Seconds to wait after each scroll
ACTION_DELAY = (1.0, 2.5)   # Random delay range between actions (seconds)
TIMEOUT = 8000               # Timeout for element waits (ms)


def random_delay():
    """Sleep for a random duration to mimic human behavior."""
    time.sleep(random.uniform(*ACTION_DELAY))


def sanitize_filename(query: str) -> str:
    """Convert a search query into a safe filename."""
    name = query.lower().strip()
    name = re.sub(r'[^a-z0-9]+', '_', name)
    name = name.strip('_')
    return f"{name}.csv"


def scroll_results(page) -> int:
    """
    Scroll the Google Maps results panel to load all listings.
    Returns the total number of result items found.
    """
    results_selector = 'div[role="feed"]'

    try:
        page.wait_for_selector(results_selector, timeout=TIMEOUT)
    except PlaywrightTimeout:
        print("  ⚠ Could not find results panel. Try a different search query.")
        return 0

    previous_count = 0
    no_change_count = 0

    for i in range(MAX_SCROLLS):
        # Scroll the feed container
        page.evaluate(f'''
            const feed = document.querySelector('{results_selector}');
            if (feed) feed.scrollTop = feed.scrollHeight;
        ''')
        time.sleep(SCROLL_PAUSE)

        # Count current results
        items = page.query_selector_all(f'{results_selector} > div > div > a')
        current_count = len(items)

        print(f"  Scroll {i+1}/{MAX_SCROLLS} — {current_count} listings loaded", end='\r')

        # Check if we've reached the end
        end_marker = page.query_selector('p.fontBodyMedium span:text("You\'ve reached the end of the list")')
        if end_marker:
            print(f"\n  ✓ Reached end of results ({current_count} listings)")
            break

        if current_count == previous_count:
            no_change_count += 1
            if no_change_count >= 3:
                print(f"\n  ✓ No more results loading ({current_count} listings)")
                break
        else:
            no_change_count = 0

        previous_count = current_count
    else:
        print(f"\n  ✓ Max scrolls reached ({current_count} listings)")

    return current_count


def extract_business_details(page) -> dict:
    """
    Extract business details from the currently open listing panel.
    Returns a dict with name, address, phone, website.
    """
    details = {
        'name': '',
        'address': '',
        'phone': '',
        'website': ''
    }

    # ── Name ──
    try:
        name_el = page.query_selector('h1.DUwDvf')
        if name_el:
            details['name'] = name_el.inner_text().strip()
    except Exception:
        pass

    # ── Address ──
    try:
        address_el = page.query_selector('button[data-item-id="address"] div.fontBodyMedium')
        if address_el:
            details['address'] = address_el.inner_text().strip()
        else:
            # Fallback: look for the address icon aria label
            address_el = page.query_selector('button[data-item-id="address"]')
            if address_el:
                aria = address_el.get_attribute('aria-label') or ''
                details['address'] = aria.replace('Address: ', '').strip()
    except Exception:
        pass

    # ── Phone ──
    try:
        # Phone buttons have data-item-id starting with "phone:"
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

    # ── Website ──
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


def scrape_google_maps(query: str) -> list[dict]:
    """
    Main scraping function.
    Searches Google Maps for the query, scrolls results, 
    clicks each listing, and extracts business details.
    """
    results = []
    seen = set()  # Track (name, address) to avoid duplicates
    search_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"

    print(f"\n🔍 Searching Google Maps for: \"{query}\"")
    print(f"   URL: {search_url}\n")

    with sync_playwright() as p:
        # Launch browser with stealth-ish settings
        browser = p.chromium.launch(
            headless=False,  # Set to True for background operation
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

        # Navigate to Google Maps search
        print("  → Opening Google Maps...")
        page.goto(search_url, wait_until='networkidle', timeout=30000)
        random_delay()

        # Handle cookie consent if it appears
        try:
            accept_btn = page.query_selector('button:has-text("Accept all")')
            if accept_btn:
                accept_btn.click()
                random_delay()
        except Exception:
            pass

        # Scroll to load all results
        print("  → Scrolling to load all results...")
        total_found = scroll_results(page)

        if total_found == 0:
            print("  ✗ No results found. Check your search query.")
            browser.close()
            return results

        # Collect all listing links
        feed_selector = 'div[role="feed"]'
        listing_links = page.query_selector_all(f'{feed_selector} > div > div > a')
        print(f"\n  → Scraping details for {len(listing_links)} businesses...\n")

        previous_name = ''
        for i, link in enumerate(listing_links):
            try:
                # Scroll the item into view and click it
                link.scroll_into_view_if_needed()
                random_delay()
                link.click()

                # Wait for the detail panel to load with a NEW business
                try:
                    page.wait_for_selector('h1.DUwDvf', timeout=TIMEOUT)
                except PlaywrightTimeout:
                    print(f"  [{i+1}/{len(listing_links)}] ⚠ Timed out — skipping")
                    continue

                # Wait for panel to actually change (avoid reading stale data)
                for _ in range(10):
                    name_el = page.query_selector('h1.DUwDvf')
                    current_name = name_el.inner_text().strip() if name_el else ''
                    if current_name and current_name != previous_name:
                        break
                    time.sleep(0.3)

                time.sleep(0.5)  # Small extra wait for all details to render

                # Extract details
                details = extract_business_details(page)
                previous_name = details['name']

                if details['name']:
                    # Deduplicate by (name, address)
                    key = (details['name'].lower(), details['address'].lower())
                    if key in seen:
                        print(f"  [{i+1}/{len(listing_links)}] ⏭ {details['name']} (duplicate, skipped)")
                        continue
                    seen.add(key)

                    results.append(details)
                    print(f"  [{i+1}/{len(listing_links)}] ✓ {details['name']}")
                    if details['phone']:
                        print(f"           📞 {details['phone']}")
                    if details['website']:
                        print(f"           🌐 {details['website']}")
                    if details['address']:
                        print(f"           📍 {details['address']}")
                else:
                    print(f"  [{i+1}/{len(listing_links)}] ⚠ No name found — skipping")

            except Exception as e:
                print(f"  [{i+1}/{len(listing_links)}] ✗ Error: {e}")
                continue

        browser.close()

    return results


def save_to_csv(results: list[dict], filename: str):
    """Save scraped results to a CSV file."""
    filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'address', 'phone', 'website'])
        writer.writeheader()
        writer.writerows(results)

    return filepath


def main():
    print("=" * 60)
    print("  Google Maps Business Lead Scraper")
    print("=" * 60)

    query = input("\n  Enter search query (e.g. 'plumbers in Dallas TX'): ").strip()

    if not query:
        print("  ✗ No query entered. Exiting.")
        return

    # Scrape
    results = scrape_google_maps(query)

    if not results:
        print("\n  ✗ No results scraped.")
        return

    # Save to CSV
    filename = sanitize_filename(query)
    filepath = save_to_csv(results, filename)

    # Summary
    print("\n" + "=" * 60)
    print(f"  ✓ Done! Scraped {len(results)} businesses")
    print(f"  📄 Saved to: {filepath}")
    print("=" * 60)

    # Quick preview
    print(f"\n  Preview (first 5 results):")
    print(f"  {'Name':<30} {'Phone':<18} {'Website':<30}")
    print(f"  {'─'*30} {'─'*18} {'─'*30}")
    for r in results[:5]:
        name = r['name'][:28] + '..' if len(r['name']) > 30 else r['name']
        phone = r['phone'] or '—'
        website = r['website'][:28] + '..' if len(r.get('website', '')) > 30 else (r.get('website') or '—')
        print(f"  {name:<30} {phone:<18} {website:<30}")


if __name__ == '__main__':
    main()
