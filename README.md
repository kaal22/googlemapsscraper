# Google Maps Business Lead Scraper

Scrape business leads from Google Maps and export to CSV.  
Extracts: **Name**, **Website**, **Phone Number**, **Address**, **Email**.

## Quick Start — Web UI

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Launch the web dashboard
python app.py
```

Open **http://localhost:5000** in your browser. From there you can:
- Enter a search query with all config options visible
- Watch live progress as the scraper runs
- View, download, and manage results from the History tab

## Quick Start — CLI

```bash
python scraper.py
```

Enter a search query when prompted. CSV files are saved to the `results/` folder.

## Configuration

All options are available in the web UI. For CLI mode, edit the top of `scraper.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `max_scrolls` | 15 | How many times to scroll the results panel |
| `scroll_pause` | 2.0s | Wait time between scrolls |
| `action_delay` | 1.0–2.5s | Random delay between clicks (stealth) |
| `timeout` | 8000ms | How long to wait for elements to appear |
| `scrape_emails` | True | Visit business websites to find emails |
| `email_timeout` | 10000ms | Timeout for loading business websites |
| `headless` | False | Run browser in background (no window) |

## Project Structure

```
google maps scraper/
├── app.py              # Flask web app
├── scraper.py           # Core scraper (importable + CLI)
├── requirements.txt     # Python dependencies
├── templates/
│   └── index.html       # Web dashboard UI
└── results/             # CSV output files (auto-created)
```

## Output

CSV files are saved in the `results/` folder, named after your query:  
`results/dentists_in_downtown_chicago_il.csv`

| name | address | phone | website | email |
|------|---------|-------|---------|-------|
| Example Dental | 123 Main St, Chicago, IL | (312) 555-0100 | exampledental.com | info@exampledental.com |
