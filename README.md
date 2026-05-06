# Store Extractor

Automated tool to extract single-store brand data from Zalora across Malaysia, Singapore, Hong Kong, and Indonesia — and export the results to Google Sheets.

## How It Works

1. **`call_api.py`** — Fetches brand IDs from each Zalora `/brands` page via the Zalora filter API, identifies brands that belong to a single store, then resolves the store name and URL.
2. **`data_crawler.py`** — Crawls Zalora search pages using `requests` + `BeautifulSoup`. Brands whose search results redirect to a single `/store` page are captured with their store name and URL.
3. **`data_exporter.py`** — Merges the results and writes them to Google Sheets using a service account.
4. **`redirect_store_extractor.py`** — Entry point that orchestrates all three steps.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Place your Google service account JSON key in the project root and update the filename reference in `data_exporter.py` if needed.

3. Run the extractor:
   ```bash
   python redirect_store_extractor.py
   ```

## Project Structure

```
redirect_store_extractor.py  # Entry point
call_api.py                  # Brand/store resolution via Zalora API
data_crawler.py              # Store discovery via search redirect crawling
data_exporter.py             # Google Sheets export
utils.py                     # Shared logging utility
requirements.txt             # Python dependencies
```

## Supported Sites

| Country | URL |
|---------|-----|
| Malaysia | https://www.zalora.com.my |
| Singapore | https://www.zalora.sg |
| Hong Kong | https://www.zalora.com.hk |
| Indonesia | https://www.zalora.co.id |
