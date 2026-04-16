# Simple Playwright Web Opener

Easy-to-use Python functions for opening web pages with Playwright.

## Quick Setup

1. Install Playwright:
   ```bash
   pip install -r requirements.txt
   playwright install
   ```

2. Run the basic example:
   ```bash
   python web_opener.py
   ```

## Usage

### Open a single website:
```python
from web_opener import open_web

# Basic usage
result = open_web("https://example.com")

# With screenshot  
result = open_web("https://github.com", screenshot=True)

# In background (headless)
result = open_web("https://python.org", headless=True)
```

### Open multiple websites:
```python
from web_opener import open_multiple_webs

sites = ["https://github.com", "https://python.org"]
results = open_multiple_webs(sites)
```

## Function Parameters

- `url` (str): Website URL to open
- `headless` (bool): Run in background (True) or show browser (False)  
- `screenshot` (bool): Save screenshot of the page

## Run Examples

```bash
python examples.py
```

This will demonstrate all the different ways to use the web opener functions.