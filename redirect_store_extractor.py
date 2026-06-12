from call_api import api_execute
from data_crawler import crawler_execute
from data_exporter import exporter_run
from utils import log

sites = [
    "https://www.zalora.com.my/brands",
    "https://www.zalora.sg/brands",
    "https://www.zalora.com.hk/brands",
    "https://www.zalora.co.id/brands",
    "https://www.zalora.com.ph/brands"
]


def main():
    fetched_data = api_execute(sites)

    # crawled_data = crawler_execute(sites)

    # Merge results, giving priority to crawler data in case of overlaps
    # result = {**crawled_data, **fetched_data}

    # Using the API is the preferred approach for now, as it offers more complete data coverage
    # Crawler cannot reliably identify the associated brand or store
    exporter_run(fetched_data)
    log("Data extraction and export completed successfully.")
    

if __name__ == "__main__":
    main()