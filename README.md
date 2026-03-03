# Google Maps Business Lead Scraper

Scrape business leads from Google Maps and export to CSV.  
Extracts: **Name**, **Website**, **Phone Number**, **Address**.

## Quick Start

```bash
# 1. Install Playwright
pip install playwright
playwright install chromium

# 2. Run the scraper
python scraper.py
```

Enter a search query when prompted (e.g. `plumbers in Dallas TX`) and the tool will:
- Open Google Maps and search for your query
- Scroll through all results to load every listing
- Click into each business to extract details
- Save everything to a CSV file (e.g. `plumbers_in_dallas_tx.csv`)

## Configuration

Edit the top of `scraper.py` to tweak:

| Setting | Default | Description |
|---------|---------|-------------|
| `MAX_SCROLLS` | 15 | How many times to scroll the results panel |
| `SCROLL_PAUSE` | 2.0s | Wait time between scrolls |
| `ACTION_DELAY` | 1.0–2.5s | Random delay between clicks (stealth) |
| `TIMEOUT` | 8000ms | How long to wait for elements to appear |

## Tips

- **More results**: Increase `MAX_SCROLLS` to load more listings
- **Faster scraping**: Decrease `ACTION_DELAY` (higher detection risk)
- **Background mode**: Set `headless=True` in `scraper.py` (line in `scrape_google_maps`)
- **Specific areas**: Be specific in your query — e.g. `"dentists in downtown Chicago IL"`

## Output

CSV files are saved in the same folder as the script, named after your query:  
`dentists_in_downtown_chicago_il.csv`

| name | address | phone | website |
|------|---------|-------|---------|
| Example Dental | 123 Main St, Chicago, IL | (312) 555-0100 | exampledental.com |
