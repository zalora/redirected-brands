from playwright.sync_api import sync_playwright, TimeoutError
import threading

result = []
store = {}

def open_web(url):
    """Open a website with Playwright"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 SHOPQAAutomation/"
        )
        page.goto(url)
        print(f"Opened: {page.title(), url}")
        result.append(fetch_brands(page))
       
        browser.close()

def fetch_brands(page):
    # page.click("//span[contains(@class, 'rounded-full')]")
    elements = page.query_selector_all("//a[contains(@class, 'text-base hover:underline')]")

    print(f"Found {len(elements)} elements")
    arr = []

    # Lặp qua từng element
    for i, el in enumerate(elements):
        try:
            arr.append(el.inner_text())
        except Exception as e:
            print(f"Error clicking element {i+1}: {e}")

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
    # print(arr_unique)

    for url in urls:
        find_single_store(arr_unique, url)

    # threads = []
    # for url in urls:
    #     thread = threading.Thread(target=find_single_store, args=(arr_unique, url,))
    #     threads.append(thread)
    #     thread.start()

    # # Wait for all to finish
    # for thread in threads:
    #     thread.join()

    print(store)
    print(len(store))

def find_single_store(arr, url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        page = browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 SHOPQAAutomation/"
        )
        url = url.replace("/brands", "")
        for brand in arr:
        
            page.goto(url+ "/search?q=" + brand)

            print(f"Searching for {brand}")
            

            try:
                if "/store" in page.url:    
                    print(f"{brand} has only 1 store")
                    url = page.url
                    print (url)
                    store[brand] = url 
                else:
                    page.wait_for_selector("//*[@data-test-id='productCount']", timeout=10000)

                    print(f"{brand} has multiple stores")

            # except TimeoutError:
            #     print(f"{brand} has only 1 store")
            #     url = page.url
            #     print (url)
            #     store[brand] = url

            except Exception as e:
                print(f"Store {brand} not found")
        browser.close()
    

def click_if_exists(page, selector):
    """Click an element if it exists"""
    try:
        element = page.query_selector(selector)
        if element:
            element.click()
            print("Clicked!")
    except Exception as e:
        print(f"Error clicking element: {e}")
    return False

# Usage
if __name__ == "__main__":
    # Open 3 sites at the same time
    sites = [
        # "https://www.zalora.com.my/brands",
        # "https://www.zalora.sg/brands", 
        "https://www.zalora.com.hk/brands"
    ]
    open_parallel(sites)