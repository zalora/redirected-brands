from data_crawler import crawler_execute
from data_exporter import exporter_run
import ast

sites = [
    "https://www.zalora.com.my/brands",
    "https://www.zalora.sg/brands",
    "https://www.zalora.com.hk/brands",
    "https://www.zalora.co.id/brands"
]

def merge_file(new_data):
    file_path = "data.txt"
    existing = {}

    try:
        with open(file_path, "r") as f:
            content = f.read().strip()
            existing = ast.literal_eval(content) if content else {}
    except FileNotFoundError:
        existing = {}


    # merge (auto overwrite)
    existing.update(new_data)

    # ghi lại
    with open(file_path, "w") as f:
        f.write(str(existing))

def main():
    # Execute data crawler
    crawled_data = crawler_execute(sites)
    print("Crawled data:", crawled_data)
    merge_file(crawled_data)
    # with open("data.txt", "a", encoding="utf-8") as f:
    #     f.write(str(crawled_data))
    print("Saved to data.txt")
    
    # Pass results to data exporter
    # exporter_run(crawled_data)

if __name__ == "__main__":
    main()