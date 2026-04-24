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


def make_session():
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
    return session

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

API_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}

final = {}
final_lock = threading.Lock()
final_data = {}


def fetch_brand_id_from_page(url):
    """Fetch brands from a /brands page using requests + BeautifulSoup"""
    session = make_session()
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
        session = make_session()
        url = f"https://api.{domain}/v1/dynproducts/datajet/filter?brandIds={brand_id}"
        res = session.get(url, headers=API_HEADERS, timeout=30)
        res.raise_for_status()

        result = res.json()
        filters = result.get("data", {}).get("Filters", [])

        stores = []
        brand = ""
        for item in filters:
            if item.get("Id") == "seller_id":
                for option in item.get("Options", []):
                    stores.append(option.get("Value"))
            if item.get("Id") == "brandIds[]":
                for option in item.get("Options", []):
                    brand = option.get("Label")

        if not brand:
            return

        with final_lock:
            final[f"{brand} - {country}"] = stores
    except Exception as e:
        log(f"Error fetching stores for brand {brand_id} in {country}: {e}")        

def remove_duplicates(data: dict) -> dict:
    store_count = Counter(
        store
        for stores in data.values()
        for store in stores
    )

    result = {
        brand: stores
        for brand, stores in data.items()
        if all(store_count[s] == 1 for s in stores)
    }
    return result

def process_site(site):
    """Process a single site: fetch brand IDs then fetch stores for each brand"""
    domain = urlparse(site).netloc.replace("www.", "")
    country = domain.split(".")[-1]

    brand_ids = fetch_brand_id_from_page(site)
    log(f"Found {len(brand_ids)} brands in {country}")

    with ThreadPoolExecutor(max_workers=10) as brand_executor:
        futures = [brand_executor.submit(fetch_stores_from_api, brand_id, domain, country) for brand_id in brand_ids]
        for future in as_completed(futures):
            future.result()  # raise exceptions if any

    log(f"Done processing {country}, total entries: {len(final)}")

def get_domain(country):
    """Get domain name based on country code"""
    domain_map = {
        "my": "zalora.com.my",
        "sg": "zalora.sg",
        "hk": "zalora.com.hk",
        "id": "zalora.co.id"
    }
    return domain_map.get(country.lower(), "")

def format_data(data):
    """Format raw data into structured format for export"""
    for brand, store_ids in data.items():
        country = brand.split(" - ")[-1]
        domain = get_domain(country)

        store_id = store_ids[0]

        try:
            url = f"https://api.{domain}/v1/seller/{store_id}"

            session = make_session()
            res = session.get(url, headers=API_HEADERS, timeout=30)
            res.raise_for_status()
            time.sleep(0.4)

            result = res.json()
            store_name = result.get("data", {}).get("SellerName")

            store_slug = slugify(store_name.lower())

            store_url = f"https://www.{domain}/store/{store_slug}"

            final_data[brand] = {
                "store_name": store_name,
                "keyword": brand.split(" - ")[0].replace(".", "").replace("'", ""),
                "url": store_url
            }

            return final_data
        except Exception as e:
            log(f"Error fetching store details for {brand}: {e}")
            return
        
def finalize_data(data):
    """Finalize data by removing duplicates and formatting for export"""
    unique_stores = remove_duplicates(data)
    log(f"Found {len(unique_stores)} unique stores after removing duplicates")

    for brand, store_id in unique_stores.items():
        print(f"Processing brand: {brand} with store ID: {store_id}")
        format_data({brand: store_id})
 
    log(f"Found {len(final_data)} stores after formatting")
    return final_data        


def api_execute(sites):
    # Process all 4 sites in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(process_site, site) for site in sites]
        for future in as_completed(futures):
            future.result()

    return finalize_data(final)


# if __name__ == "__main__":
#     api_execute() 