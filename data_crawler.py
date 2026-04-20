import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from utils import log
from collections import Counter

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 SHOPQAAutomation/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_thread_local = threading.local()
_lock = threading.Lock()


def get_session():
    """Return a thread-local requests session with retry logic."""
    if not hasattr(_thread_local, "session"):
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _thread_local.session = session
    return _thread_local.session


def fetch_brand_from_url(url):
    """Fetch a /brands page and return {brand_name: href} dict."""
    log(f"Opening {url}")
    session = get_session()
    res = session.get(url, headers=HEADERS, timeout=30)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    elements = soup.find_all(
        "a", class_=lambda x: x and "text-base" in x and "hover:underline" in x
    )
    brands = {
        el.get_text(strip=True): el.get("href")
        for el in elements
        if el.get_text(strip=True)
    }
    log(f"Found {len(brands)} brands from {url}")
    return brands


def process_brand(base_url, country, brand, result):
    """Search for a brand and record it if the search redirects to a single store."""
    brand_keyword = brand.replace(".", "").replace("'", "")
    search_url = f"{base_url}/search?q={quote(brand_keyword)}"

    try:
        session = get_session()
        res = session.get(search_url, headers=HEADERS, timeout=30, allow_redirects=True)
        final_url = res.url

        if "/store" not in final_url:
            return

        log(f"{brand.title()} - {country.upper()} found in 1 store")

        soup = BeautifulSoup(res.text, "html.parser")
        store_name = ""
        store_header = soup.find(id="zis-store-header")
        if store_header:
            h1 = store_header.find("h1")
            if h1:
                store_name = h1.get_text(strip=True)

        keyword1 = brand.split(" - ")[0].lower()
        keyword2 = re.sub(r'[^a-zA-Z0-9 ]', '', brand.split(" - ")[0])        

        with _lock:
            result[f"{brand} - {country}"] = {
                "store_name": store_name,
                "keyword": [keyword1, keyword2],
                "url": final_url,
            }

    except Exception as e:
        log(f"Error searching for {brand.title()}: {e}")


def find_redirect_stores(brand_list, url, result, num_workers=10):
    """Process all brands for a site URL using a thread pool."""
    base_url = url.replace("/brands", "")
    country = base_url.rstrip("/")[-2:]

    if not brand_list:
        return

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [
            executor.submit(process_brand, base_url, country, brand, result)
            for brand in brand_list
        ]
        for future in as_completed(futures):
            future.result()


def extract_brands_data(urls):
    """Fetch brands from each URL then find single-store brands."""
    result = {}

    def process_site(url):
        brands = fetch_brand_from_url(url)
        find_redirect_stores(brands, url, result)

    with ThreadPoolExecutor(max_workers=len(urls)) as executor:
        futures = [executor.submit(process_site, url) for url in urls]
        for future in as_completed(futures):
            future.result()

    log(f"{len(result)} redirect stores have been processed.")
    return result


def crawler_execute(urls):
    """Entry point: execute the brand crawling process for the given URLs."""
    return extract_brands_data(urls)