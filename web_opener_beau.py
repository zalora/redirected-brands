

import datetime

import requests
from bs4 import BeautifulSoup
import threading

result = []
store = {}


def log(msg):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")


def open_web(url):
    """Open a website with requests and BeautifulSoup"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 SHOPQAAutomation/'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        log(url)
        result.append(fetch_brands(soup))
        
    except requests.RequestException as e:
        print(f"Error opening {url}: {e}")
        result.append([])

def fetch_brands(soup):
    # Find elements with class containing 'text-base hover:underline'
    elements = soup.find_all('a', class_=lambda x: x and 'text-base' in x and 'hover:underline' in x)

    print(f"Found {len(elements)} elements")
    arr = []

    # Loop through each element
    for i, el in enumerate(elements):
        try:
            text = el.get_text(strip=True)
            if text:
                arr.append(text)
        except Exception as e:
            print(f"Error processing element {i+1}: {e}")

    return arr      

def open_parallel(urls):
    """Open multiple websites at the same time"""
    threads = []
    for url in urls:
        thread = threading.Thread(target=open_web, args=(url,))
        threads.append(thread)
        thread.start()
    
    # Wait for all to finish
    for thread in threads:
        thread.join()

    merged = [item for sublist in result for item in sublist]  
    arr_unique = list(dict.fromkeys(merged))
    print(len(arr_unique))

    # for url in urls:
    #     find_single_store(arr_unique, url)

    threads = []
    for url in urls:
        thread = threading.Thread(target=find_single_store, args=(arr_unique, url,))
        threads.append(thread)
        thread.start()

    # Wait for all to finish
    for thread in threads:
        thread.join()

    msg = store
    log(msg)
    print(len(store))

def find_single_store(arr, url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 SHOPQAAutomation/'
    }
    
    base_url = url.replace("/brands", "")
    country = base_url[-2:]
    
    for brand in arr:
        search_url = f"{base_url}/search?q={brand}"
        
        try:
            response = requests.get(search_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # msg = f"Searching for {brand}"
            # log(msg)
            
            # Check if redirected to store page
            if "/store" in response.url:    
                msg = f"{brand} - {country} has only 1 store"
                log(msg)
                store[brand + "-" + country] = response.url

            # else:
            #     # Parse the page to look for product count or store info
            #     # soup = BeautifulSoup(response.content, 'html.parser')

            #     # print(soup)
                
            #     # # Look for product count element
            #     # product_count = soup.find('span', string=lambda text: text and 'items found' in text.lower())
            #     # if product_count:
            #         # print(f"Found products for {brand}: {product_count.get_text(strip=True)}")
            #     # else:
            #     msg = f"No specific product count found for {brand}"
            #     log(msg)
                    
        except requests.RequestException as e:
            print(f"Error searching for {brand}: {e}")
            continue

def element_exists(soup, selector):
    """Check if an element exists in the soup"""
    try:
        # Convert CSS selector or use find method
        element = soup.select_one(selector) if selector.startswith('.') or selector.startswith('#') else soup.find(attrs={'data-test-id': selector})
        if element:
            print("Element found!")
            return True
        return False
    except Exception as e:
        print(f"Error finding element: {e}")
        return False

# Usage
if __name__ == "__main__":
    # Open 3 sites at the same time
    sites = [
        # "https://www.zalora.com.my/brands",
        "https://www.zalora.sg/brands", 
        "https://www.zalora.com.hk/brands"
    ]
    open_parallel(sites)