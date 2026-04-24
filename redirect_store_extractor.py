from call_api import api_execute
from data_crawler import crawler_execute
from data_exporter import exporter_run
import ast

sites = [
    "https://www.zalora.com.my/brands",
    "https://www.zalora.sg/brands",
    "https://www.zalora.com.hk/brands",
    "https://www.zalora.co.id/brands"
]


def main():
    fetched_data = api_execute(sites)

    crawled_data = crawler_execute(sites)

    result = {**fetched_data, **crawled_data}

    exporter_run(result)
    print("Data extraction and export completed successfully.")
    

if __name__ == "__main__":
    main()