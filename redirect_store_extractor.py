from call_api import api_execute
from data_crawler import crawler_execute
from data_exporter import exporter_run
from utils import log

sites = [
    "https://www.zalora.com.my/brands",
    "https://www.zalora.sg/brands",
    "https://www.zalora.com.hk/brands",
    "https://www.zalora.co.id/brands"
]


def main():
    fetched_data = api_execute(sites)

    crawled_data = crawler_execute(sites)

    # Merge results, giving priority to crawler data in case of overlaps
    result = {**crawled_data, **fetched_data}

    exporter_run(result)
    log("Data extraction and export completed successfully.")
    

if __name__ == "__main__":
    main()