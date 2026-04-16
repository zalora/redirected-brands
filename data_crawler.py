import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import quote
from utils import log

all_brands_result = []
all_redirect_stores = {}



async def fetch_brand_from_url(session, url):
    """Fetch webpage content from a URL and extract all brands from it"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 SHOPQAAutomation/'
    }
    
    try:
        log(f"Opening {url}")
        async with session.get(url, headers=headers, timeout=10) as response:
            response.raise_for_status()

            content = await response.text()
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



async def find_redirect_store(session, brand_list, url):
    """Check which brands redirect to their own store page (single store brands)"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 SHOPQAAutomation/'
    }
    
    base_url = url.replace("/brands", "")
    country = base_url[-2:]

    
    for brand in brand_list:
        # Remove dots and apostrophes from brand name for better search results
        brand_keyword = brand.replace(".", "").replace("'", "")
        # URL encode the brand name
        encoded_brand = quote(brand_keyword)
        search_url = f"{base_url}/search?q={encoded_brand}"
        
        try:
            async with session.get(search_url, headers=headers, timeout=10) as response:
                response.raise_for_status()
                
                # Check if redirected to store page
                if "/store" in str(response.url):    
                    msg = f"{brand.title()} - {country.upper()} found in 1 store"
                    log(msg)

                    # Extract store name from the redirected page
                    content = await response.text()
                    webpage_content = BeautifulSoup(content, 'html.parser')
                    store_name = webpage_content.find(id='zis-store-header').find('h1').get_text(strip=True)

                    row = {
                        "store_name": store_name,
                        "keyword": brand_keyword,
                        "url": str(response.url)
                    }

                    all_redirect_stores[brand + "-" + country] = row
            
        except Exception as e:
            if "404" in str(e) and "/store" in str(response.url):
                log(f"{brand.title()} - {country.upper()} found in 1 store - URL returned 404")

                row = {
                    "store_name": "",
                    "keyword": brand_keyword,
                    "url": str(response.url)
                }

                all_redirect_stores[brand + "-" + country] = row
            else:
                log(f"Error searching for {brand.title()}: {e}")    

        except aiohttp.ClientError as e:
            log(f"Other request error searching for {brand.title()}: {e}")


async def element_exists(webpage_content, selector):
    """Check if a specific element exists on the webpage"""
    try:
        log(f"Checking for element: {selector}")
        element = webpage_content.find(attrs={'data-test-id': selector})
        if element:
            log("Element found!")
            return True
        return False
    except Exception as e:
        log(f"Error finding element: {e}")
        return False
    


async def extract_brands_data(urls):
    """Main function to extract brands from multiple URLs and find single-store brands"""
    async with aiohttp.ClientSession() as session:
        # crawl data for all URLs
        tasks = [fetch_brand_from_url(session, url) for url in urls]
        await asyncio.gather(*tasks)

    # merge and deduplicate brand lists from all URLs
    merged = [item.lower() for sublist in all_brands_result for item in sublist]  
    brand_list_unique = list(dict.fromkeys(merged))

    # identify global store redirects using a unique cross-country brand list
    log (f"Finding {len(brand_list_unique)} redirect stores")
    async with aiohttp.ClientSession() as session:
        tasks = [find_redirect_store(session, brand_list_unique, url) for url in urls]
        await asyncio.gather(*tasks)

    log(f"{len(all_redirect_stores)} redirect stores have been processed.")  
    return all_redirect_stores


def crawler_execute(urls):
    """Execute the brand crawling process for the given URLs"""
    return asyncio.run(extract_brands_data(urls))