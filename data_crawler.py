import asyncio
from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError
from bs4 import BeautifulSoup
from urllib.parse import quote
from utils import log
from collections import Counter
from slugify import slugify

all_brands_result = []
all_redirect_stores = {}
final_result = {}
gift_promotion_dismissed = None
gift_promotion_lock = None


async def fetch_brand_from_url(page, url):
    """Fetch webpage content from a URL and extract all brands from it"""
    try:
        log(f"Opening {url}")
        response = await page.goto(url)
        
        if response and response.status >= 400:
            raise Exception(f"HTTP {response.status}")

        content = await page.content()
        webpage_content = BeautifulSoup(content, 'html.parser')  # Built-in parser
        
        all_brands_result.clear()  # Clear previous results
        brands = get_all_brands(webpage_content)
        all_brands_result.append(brands)
        
        # Cleanup BeautifulSoup object
        webpage_content.decompose()
        del webpage_content, content
        
    except Exception as e:
        log(f"Error opening {url}: {e}")
        all_brands_result.append([])



def get_all_brands(webpage_content):
    """Extract all brand names from the webpage content"""
    try:
        # Find brands elements
        elements = webpage_content.find_all('a', class_=lambda x: x and 'text-base' in x and 'hover:underline' in x)
        
        # Extract text directly in generator to save memory
        brands = {
            el.get_text(strip=True): el.get("href")
            for el in elements
            if el.get_text(strip=True)
        }
        
                
        log(f"Found {len(brands)} brands")
        return brands
    except Exception as e:
        log(f"Error extracting brands: {e}")
        return []      


async def process_brand(page, base_url, country, brand, brand_url):

    """Process a single brand search task"""
    global gift_promotion_dismissed, gift_promotion_lock
    
    # Remove dots and apostrophes from brand name for better search results
    brand_keyword = brand.replace(".", "").replace("'", "")
    search_url = f"{base_url}/search?q={quote(brand_keyword)}"
    
    response = None
    try:
        response = await page.goto(search_url)
        
        if not response:
            raise Exception("No response received")
            
        current_url = page.url
        
        # Check if redirected to store page
        if "/store" in current_url:    
            log(f"{brand.title()} - {country.upper()} found in 1 store")

            # Extract store name from the redirected page
            content = await page.content()
            webpage_content = BeautifulSoup(content, 'html.parser')
            
            store_name = ""
            store_header = webpage_content.find(id='zis-store-header')
            if store_header:
                h1_tag = store_header.find('h1')
                if h1_tag:
                    store_name = h1_tag.get_text(strip=True)

            all_redirect_stores[f"{brand}-{country}"] = {
                "store_name": [store_name],
                "keyword": brand_keyword,
                "url": current_url
            }
        else:
            async with gift_promotion_lock:
                if not gift_promotion_dismissed:
                    await click_if_exists(page, "//*[@data-test-id='giftPromotionOnboardingGotIt']")
                    gift_promotion_dismissed = True
            await find_store(page, brand, country, brand_url)
        
    except Exception as e:
        current_url = getattr(page, 'url', '')
        if response and response.status == 404 and "/store" in current_url:
            log(f"{brand.title()} - {country.upper()} found in 1 store - URL returned 404")
            all_redirect_stores[f"{brand}-{country}"] = {
                "store_name": [""],
                "keyword": brand_keyword,
                "url": current_url
            }
        else:
            log(f"Error searching for {brand.title()}: {e}")


async def find_redirect_store(browser_context, brand_list, url, num_workers=10):
    """Process brands using shared browser context"""
    base_url = url.replace("/brands", "")
    country = base_url[-2:]
    
    if not brand_list:
        return
    
    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(num_workers)
    
    # Optimize batch size for higher worker count
    batch_size = max(2, len(brand_list) // (num_workers * 3))  # Larger batches for efficiency
    
    async def process_batch(brands):
        """Process a batch of brands using a single page"""
        async with semaphore:
            page = await browser_context.new_page()
            try:
                for brand, brand_url in brands:
                    await process_brand(page, base_url, country, brand, brand_url)
            finally:
                await page.close()
    
    # Process batches in smaller groups to reduce memory pressure
    tasks = []
    for i in range(0, len(brand_list), batch_size):
        batch = list(brand_list.items())[i:i + batch_size]
        if batch:
            tasks.append(asyncio.create_task(process_batch(batch)))
            
            # Process in small groups to avoid memory spikes
            if len(tasks) >= num_workers:
                await asyncio.gather(*tasks)
                tasks.clear()
    
    # Process remaining tasks
    if tasks:
        await asyncio.gather(*tasks)

    result = await remove_duplicate(all_redirect_stores)
    final_result.update(result)
    
    log(f"Completed processing {len(brand_list)} brands for {country.upper()}")


async def find_store(page, brand, country, brand_url):
    current_url = getattr(page, 'url', '')
    if "brandIds" not in current_url:
        await page.goto(brand_url)     

    await page.evaluate("window.scrollTo(0, 1000)")

    try:
        await page.wait_for_selector("//*[@data-test-value='seller_id']", timeout=3000)
        view_store_button = page.locator("//*[@data-test-value='seller_id']")
        await view_store_button.click(timeout=2000)

        await asyncio.sleep(1)  # wait for the store page to load after clicking the button

        store_count = await page.locator("//*[@data-test-id='selectOption']").count()
        stores = await page.locator("//*[@data-test-id='selectOption']").evaluate_all(
            "elements => elements.map(el => el.getAttribute('data-test-value'))"
        )

        if store_count > 0:
            log(f"{brand.title()} - {country.upper()} has store[s]")
            brand_keyword = brand.replace(".", "").replace("'", "")
            all_redirect_stores[f"{brand}-{country}"] = {
                "store_name": stores,
                "keyword": brand_keyword,
                "url": country_url.replace("/brands", f"/store/{slugify(brand.lower())}")
            }
            return
        else:
            # log(f"{brand.title()} - {country.upper()} has no store")  
            return  

    except TimeoutError:
        log(f"{brand.title()} - {country.upper()} has no store (timeout)")
    except Exception as e:
        log(f"{brand.title()} - {country.upper()} has no store or error occurred: {e}")

async def remove_duplicate(data):
    store_count = Counter(s for v in data.values() for s in v["store_name"])

    # remove brands that have duplicated store names
    unique_data = {
        k: v for k, v in data.items()
        if all(store_count[s] == 1 for s in v["store_name"])
    }

    # remove brands that have more than 1 store
    result = {
        k: v
        for k, v in unique_data.items()
        if len(v["store_name"]) == 1
    }

    return result

async def extract_brands_data(urls):
    """Main function to extract brands from multiple URLs and find single-store brands"""
    global gift_promotion_lock, gift_promotion_dismissed, all_brands_result, all_redirect_stores, country_url
    
    # Initialize the lock and reset dismissed state for this execution
    gift_promotion_lock = asyncio.Lock()
    gift_promotion_dismissed = False
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            permissions=[],
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 SHOPQAAutomation/"
        )

        # crawl data for all URLs sequentially to reduce memory
        for url in urls:
            country_url = url
            page = await context.new_page()
            try:
                await fetch_brand_from_url(page, url)
            finally:
                await page.close()
        
        # Process each URL sequentially to reduce memory pressure  
        for url in urls:
            all_redirect_stores.clear()  # Clear memory after processing
            await find_redirect_store(context, all_brands_result[0], url)
        
        await browser.close()

    log(f"{len(all_redirect_stores)} redirect stores have been processed.")

    log(f"Final result: {len(final_result)}")
    return final_result

async def click_if_exists(page, selector):
    """Click an element if it exists"""
    try:
        element = await page.wait_for_selector(selector, timeout=3000)  # Shorter timeout
        if element:
            await element.click()
            return True
    except Exception:
        pass  # Ignore errors silently
    return False

def crawler_execute(urls):
    """Execute the brand crawling process for the given URLs"""
    return asyncio.run(extract_brands_data(urls))