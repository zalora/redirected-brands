import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import re
from utils import log
from collections import Counter
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
from slugify import slugify


_thread_local = threading.local()


def get_session():
    """Return a thread-local session with retry logic."""
    if not hasattr(_thread_local, "session"):
        session = requests.Session()
        retry = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _thread_local.session = session
    return _thread_local.session

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

API_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}

DOMAIN_MAP = {
    "my": "zalora.com.my",
    "sg": "zalora.sg",
    "hk": "zalora.com.hk",
    "id": "zalora.co.id",
}

final = {}
final_lock = threading.Lock()
final_data = {}
final_data_lock = threading.Lock()


def build_brand_key(brand, country):
    return f"{brand} - {country}"


def fetch_brand_id_from_page(url):
    """Fetch brands from page using requests + BeautifulSoup"""
    session = get_session()
    res = session.get(url, headers=HEADERS, timeout=30)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    elements = soup.find_all("a", class_=lambda x: x and "text-base" in x and "hover:underline" in x)

    brand_id = {
        re.search(r'(\d+)$', el.get("href")).group(1)
        for el in elements
        if el.get_text(strip=True)
    }
    return brand_id


def fetch_stores_from_api(brand_id, domain, country):
    """Fetch stores for a brand from the Zalora filter API"""
    try:
        session = get_session()
        url = f"https://api.{domain}/v1/dynproducts/datajet/filter?brandIds={brand_id}"
        res = session.get(url, headers=API_HEADERS, timeout=30)
        res.raise_for_status()

        result = res.json()
        filters = result.get("data", {}).get("Filters", [])

        stores = []
        brand = ""
        for item in filters:
            if item.get("Id") == "seller_id":
                options = item.get("Options", [])
                for option in options:
                    stores.append(option.get("Value"))
            if item.get("Id") == "brandIds[]":
                for option in item.get("Options", []):
                    brand = option.get("Label")

        if not brand:
            return

        with final_lock:
            final[build_brand_key(brand, country)] = stores

    except Exception as e:
        log(f"[API] Error fetching stores for brand {brand_id} in {country}: {e}")        

def remove_duplicates(data: dict) -> dict:
    def normalize_store_id(store_id):
        return str(store_id).strip()

    def normalize_country(brand_key):
        return brand_key.rsplit(" - ", 1)[-1].strip().upper()

    # Count normalized (store_id, country) pairs.
    store_country_count = Counter(
        (normalize_store_id(store), normalize_country(brand))
        for brand, stores in data.items()
        for store in stores
    )

    duplicated_pairs = {
        pair
        for pair, count in store_country_count.items()
        if count > 1
    }

    result = {
        brand: stores
        for brand, stores in data.items()
        if stores and all(
            (normalize_store_id(store), normalize_country(brand)) not in duplicated_pairs
            for store in stores
        )
    }

    # After duplicate removal, drop brands sold by 2+ stores
    result = {
        brand: stores
        for brand, stores in result.items()
        if len(stores) < 2
    }
    return result

def process_site(site):
    """Process a single site: fetch brand IDs then fetch stores for each brand"""
    domain = urlparse(site).netloc.replace("www.", "")
    country = domain.split(".")[-1]

    brand_ids = fetch_brand_id_from_page(site)
    log(f"[API] Found {len(brand_ids)} brands in {country.upper()} from {site}")

    with ThreadPoolExecutor(max_workers=10) as brand_executor:
        futures = [brand_executor.submit(fetch_stores_from_api, brand_id, domain, country) for brand_id in brand_ids]
        for future in as_completed(futures):
            future.result()

    log(f"[API] Done processing API in {country.upper()}")

def get_domain(country):
    """Get domain name based on country code"""
    return DOMAIN_MAP.get(country.lower(), "")


def build_keywords(brand_key):
    """Build keyword variants from brand key in format '<brand> - <country>'."""
    brand_name = brand_key.rsplit(" - ", 1)[0]
    keyword1 = brand_name.lower()
    if keyword1.endswith("."):
        keyword1 = keyword1[:-1]
    keyword2 = re.sub(r'[^a-zA-Z0-9 ]', '', brand_name)
    return [keyword1, keyword2]

def format_data(brand, store_ids):
    """Format a single brand record into export shape and store in shared final_data."""
    country = brand.rsplit(" - ", 1)[-1]
    domain = get_domain(country)
    if not domain or not store_ids:
        return

    store_id = store_ids[0]

    try:
        session = get_session()
        seller_info_url = f"https://api.{domain}/v1/dynseller/{store_id}/datajet/section/home"
        seller_info_res = session.get(seller_info_url, headers=API_HEADERS, timeout=30)
        seller_info_res.raise_for_status()
        time.sleep(0.4)
        seller_info_url_result = seller_info_res.json()

        subsections = seller_info_url_result.get("data", {}).get("Subsections", [])
        final_store_name = None
        final_store_slug = None
        for subsection in subsections:
            collection = subsection.get("Collection") or {}
            product_list = collection.get("ProductList") or {}
            products = product_list.get("Products") or []
            if not products:
                continue
            fulfillment = products[0].get("FulfillmentInformation") or {}
            final_store_name = fulfillment.get("SellerName") or final_store_name
            final_store_slug = fulfillment.get("SellerUrlKey") or final_store_slug
            if final_store_name and final_store_slug:
                break

        # Fallback to seller API only when missing name or slug from seller info endpoint
        if final_store_name is None or final_store_slug is None:
            seller_name_url = f"https://api.{domain}/v1/seller/{store_id}"
            seller_name_res = session.get(seller_name_url, headers=API_HEADERS, timeout=30)
            seller_name_res.raise_for_status()
            time.sleep(0.4)
            seller_name_result = seller_name_res.json()

            fallback_name = seller_name_result.get("data", {}).get("SellerName")
            if final_store_name is None:
                final_store_name = fallback_name
            if final_store_slug is None and fallback_name:
                final_store_slug = slugify(fallback_name.lower())

        if not final_store_name or not final_store_slug:
            raise ValueError(f"Missing seller name/slug for store_id={store_id}")

        final_store_url = f"https://www.{domain}/store/{final_store_slug}"

        with final_data_lock:
            final_data[brand] = {
                "store_name": final_store_name,
                "keyword": build_keywords(brand),
                "url": final_store_url,
            }
    except Exception as e:
        log(f"[API] Error fetching store details for {brand}: {e}")
        
def finalize_data(data):
    """Finalize data by removing duplicates and formatting for export"""
    unique_stores = remove_duplicates(data)
    log(f"[API] Found {len(unique_stores)} unique stores after removing duplicates")

    log("[API] Starting to format data for export...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(format_data, brand, store_ids) for brand, store_ids in unique_stores.items()]
        for future in as_completed(futures):
            future.result()

    log(f"[API] Found {len(final_data)} stores after formatting")
    return final_data        


def api_execute(sites):
    with final_lock:
        final.clear()
    with final_data_lock:
        final_data.clear()

    # Process all 4 sites in parallel
    log("Starting API data extraction...")
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(process_site, site) for site in sites]
        for future in as_completed(futures):
            future.result()

    return finalize_data(final)