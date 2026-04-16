import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import quote
from utils import log

all_brands_result = []
all_redirect_stores = {}
gift_promotion_dismissed = False
gift_promotion_lock = None



async def fetch_brand_from_url(page, url):
    """Fetch webpage content from a URL and extract all brands from it"""
    try:
        log(f"Opening {url}")
        response = await page.goto(url)
        
        if response and response.status >= 400:
            raise Exception(f"HTTP {response.status}")

        content = await page.content()
        webpage_content = BeautifulSoup(content, 'html.parser')
        
        all_brands_result.append(get_all_brands(webpage_content))
        
    except Exception as e:
        log(f"Error opening {url}: {e}")
        all_brands_result.append([])



def get_all_brands(webpage_content):
    """Extract all brand names from the webpage content"""
    brand_list = []

    # Find brands elements
    elements = webpage_content.find_all('a', class_=lambda x: x and 'text-base' in x and 'hover:underline' in x)

    log(f"Found {len(elements)} brands")
    
    for i, el in enumerate(elements):
        try:
            text = el.get_text(strip=True)
            if text:
                brand_list.append(text)
        except Exception as e:
            log(f"Error processing element {i+1}: {e}")

    return brand_list      



def group_brands_by_alphabet(brand_list):
    """Group brands by their first letter"""
    alphabet_groups = {}
    
    for brand in brand_list:
        first_letter = brand[0].upper() if brand else 'OTHER'
        if first_letter not in alphabet_groups:
            alphabet_groups[first_letter] = []
        alphabet_groups[first_letter].append(brand)
    
    log(f"Grouped brands into {len(alphabet_groups)} alphabet groups")
    
    return alphabet_groups


async def brand_worker(worker_id, queue, page, base_url, country):
    """Worker function that processes brand search tasks from queue"""
    global gift_promotion_dismissed, gift_promotion_lock
    
    while True:
        try:
            # Get a brand to process from queue
            brand = await asyncio.wait_for(queue.get(), timeout=1.0)
            
            # Remove dots and apostrophes from brand name for better search results
            brand_keyword = brand.replace(".", "").replace("'", "")
            # URL encode the brand name
            encoded_brand = quote(brand_keyword)
            search_url = f"{base_url}/search?q={encoded_brand}"
            
            try:
                response = await page.goto(search_url)
                
                if not response:
                    raise Exception("No response received")
                    
                current_url = page.url
                
                # Check if redirected to store page
                if "/store" in current_url:    
                    msg = f"{brand.title()} - {country.upper()} found in 1 store"
                    log(msg)

                    # Extract store name from the redirected page
                    content = await page.content()
                    webpage_content = BeautifulSoup(content, 'html.parser')
                    
                    store_name = ""
                    store_header = webpage_content.find(id='zis-store-header')
                    if store_header:
                        h1_tag = store_header.find('h1')
                        if h1_tag:
                            store_name = h1_tag.get_text(strip=True)

                    row = {
                        "store_name": store_name,
                        "keyword": brand_keyword,
                        "url": current_url
                    }

                    all_redirect_stores[brand + "-" + country] = row
                else:
                    try:
                        async with gift_promotion_lock:
                            if not gift_promotion_dismissed:
                                await click_if_exists(page, "//*[@data-test-id='giftPromotionOnboardingGotIt']")
                                gift_promotion_dismissed = True
                        await find_store(page, brand, country)

                    except Exception as e:
                        log(f"{brand} - no product count found: {e}")    
                
            except Exception as e:
                try:
                    current_url = page.url
                    if response and response.status == 404 and "/store" in current_url:
                        log(f"{brand.title()} - {country.upper()} found in 1 store - URL returned 404")

                        row = {
                            "store_name": "",
                            "keyword": brand_keyword,
                            "url": current_url
                        }

                        all_redirect_stores[brand + "-" + country] = row
                    else:
                        log(f"Error searching for {brand.title()}: {e}")
                except Exception as e:
                    log(f"Error searching for {brand.title()}: {e}")
            
            # Mark task as done
            queue.task_done()
            
        except asyncio.TimeoutError:
            # No more items in queue, exit worker
            # log(f"Worker {worker_id} for {country.upper()} finished - no more tasks")
            break
        except Exception:
            # log(f"Worker {worker_id} error: {e}")
            queue.task_done()


async def find_redirect_store(brand_list, url, num_workers=8):
    """Process brands using queue-based workers"""
    base_url = url.replace("/brands", "")
    country = base_url[-2:]
    
    # if brand_list:
    #     log(f"Processing {len(brand_list)} brands for {country.upper()} using {num_workers} workers")
    
    # Create queue and add all brands
    queue = asyncio.Queue()
    for brand in brand_list:
        await queue.put(brand)
    
    # Create browser context for workers
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            permissions=[],
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 SHOPQAAutomation/"
        )
        
        # Create worker tasks
        workers = []
        for i in range(num_workers):
            page = await context.new_page()
            worker = asyncio.create_task(brand_worker(i, queue, page, base_url, country))
            workers.append(worker)
        
        # Wait for all tasks to be processed
        await queue.join()
        
        # Cancel remaining workers
        for worker in workers:
            worker.cancel()
        
        await browser.close()
    
    log(f"Completed processing brands for {country.upper()}")


async def find_store(page, brand, country):
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    # await asyncio.sleep(2)
    try:
        await page.wait_for_selector("//*[@data-test-value='seller_id']", timeout=10000)
        view_store_button = page.locator("//*[@data-test-value='seller_id']")
        await view_store_button.click()

        await asyncio.sleep(1)  # wait for the store page to load after clicking the button

        # await page.wait_for_selector("//*[@data-test-id='selectOption']", timeout=3000)
        store_count = await page.locator("//*[@data-test-id='selectOption']").count()
        stores = await page.locator("//*[@data-test-id='selectOption']").evaluate_all(
            "elements => elements.map(el => el.getAttribute('data-test-value'))"
        )
        # print(stores)
        # print(f"Stores - {brand.title()} - {country.upper()}: {store_count}")
        if 'ZALORA' in stores or 'Sasa' in stores or 'Strawberry' in stores:
            return

        if store_count > 1:
            # log(f"{brand.title()} - {country.upper()} has multiple stores")
            return
        elif store_count == 0:
            log(f"{brand.title()} - {country.upper()} has no store")     
        else:
            log(f"{brand.title()} - {country.upper()} has ONLY 1 store")
    except Exception:
        log(f"{brand.title()} - {country.upper()} has no store or error occurred")



async def extract_brands_data(urls):
    """Main function to extract brands from multiple URLs and find single-store brands"""
    global gift_promotion_lock, gift_promotion_dismissed
    
    # Initialize the lock and reset dismissed state for this execution
    gift_promotion_lock = asyncio.Lock()
    gift_promotion_dismissed = False
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            permissions=[],
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 SHOPQAAutomation/"
        )

        
        # crawl data for all URLs
        tasks = []
        for url in urls:
            page = await context.new_page()
            tasks.append(fetch_brand_from_url(page, url))
        
        await asyncio.gather(*tasks)
        
        # Close pages after brand fetching
        for page in context.pages:
            await page.close()

        # merge and deduplicate brand lists from all URLs
        merged = [item.lower() for sublist in all_brands_result for item in sublist]  
        brand_list_unique = list(dict.fromkeys(merged))

        # Group brands by alphabet
        alphabet_groups = group_brands_by_alphabet(brand_list_unique)

        # Process redirect stores using queue-based workers
        log(f"Finding redirect stores for {len(brand_list_unique)} brands across {len(alphabet_groups)} alphabet groups")
        
        tasks = []
        for url in urls:
            for letter, brands in alphabet_groups.items():
                tasks.append(find_redirect_store(brands, url))
        
        await asyncio.gather(*tasks)
        
        await browser.close()

    log(f"{len(all_redirect_stores)} redirect stores have been processed.")  
    return all_redirect_stores

async def click_if_exists(page, selector):
    """Click an element if it exists"""
    try:
        element = await page.wait_for_selector(selector, timeout=5000)
        if element:
            await element.click()
            print("Clicked!")
            return True
    except Exception as e:
        print(f"Error clicking element: {e}")
    return False

def crawler_execute(urls):
    """Execute the brand crawling process for the given URLs"""
    return asyncio.run(extract_brands_data(urls))