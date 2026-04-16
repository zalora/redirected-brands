import datetime

from playwright.async_api import async_playwright
import asyncio

result = []
store = {}

def log(msg):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")

async def open_web(url):
    """Open a website with Playwright async"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            permissions=[],
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 SHOPQAAutomation/"
        )

        page = await context.new_page()
        await page.goto(url)
        log(url)
        
        brands = await fetch_brands(page)
        result.append(brands)
       
        await browser.close()

async def fetch_brands(page):
    """Fetch brand elements from page"""
    elements = await page.query_selector_all("//a[contains(@class, 'text-base hover:underline')]")

    print(f"Found {len(elements)} elements")
    arr = []

    # Loop through each element
    for i, el in enumerate(elements):
        try:
            text = await el.inner_text()
            arr.append(text)
        except Exception as e:
            print(f"Error processing element {i+1}: {e}")

    return arr      

async def open_parallel(urls):
    """Open multiple websites at the same time"""
    # Create tasks for all URLs
    tasks = [open_web(url) for url in urls]
    
    # Wait for all to finish
    await asyncio.gather(*tasks)

    merged = [item for sublist in result for item in sublist]  
    arr_unique = list(dict.fromkeys(merged))
    print(len(arr_unique))

    # Create tasks for finding single stores
    tasks = [find_single_store(arr_unique, url) for url in urls]
    await asyncio.gather(*tasks)

    print(store)
    print(len(store))

async def find_single_store(arr, url):
    """Find single stores for brands using async Playwright"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            permissions=[],
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 SHOPQAAutomation/"
        )

        page = await context.new_page()

        base_url = url.replace("/brands", "")
        
        for brand in arr:
            try:
                await page.goto(base_url)
                

                await page.wait_for_selector("//*[@id='header_search']", timeout=10000)

                search_bar = await page.query_selector("//*[@id='header_search']")
                await search_bar.type(brand, delay=50)
                await search_bar.press("Enter")

                print(f"Searching for {brand}")

                await asyncio.sleep(2)
                
                await click_if_exists(page, "//*[@data-test-id='giftPromotionOnboardingGotIt']")

                current_url = page.url
                if "/store" in current_url:    
                    log(f"{brand} has only 1 store")
                    log(current_url)
                    store[brand] = current_url 
                else:
                    try:
                        await page.locator("//*[@data-test-id='productCount']").wait_for(timeout=10000)
                        log(f"{brand} has multiple stores")
                    except Exception as e:
                        log(f"{brand} - no product count found: {e}")

            except Exception as e:
                print(f"Store {brand} not found: {e}")
                
        await browser.close()

async def click_if_exists(page, selector):
    """Click an element if it exists"""
    try:
        element = await page.query_selector(selector)
        if element:
            await element.click()
            print("Clicked!")
            return True
    except Exception as e:
        print(f"Error clicking element: {e}")
    return False

# Usage
if __name__ == "__main__":
    # Open 3 sites at the same time
    sites = [
        # "https://www.zalora.com.my/brands",
        # "https://www.zalora.sg/brands", 
        "https://www.zalora.com.my/brands"
    ]
    asyncio.run(open_parallel(sites))