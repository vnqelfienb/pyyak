import trio

from pyyak.core.config import SpiderConfig
from pyyak.core.spider import Spider


async def main():
    # Step 1: Define the crawler configuration
    config = SpiderConfig(
        base_url="https://www.olx.bg/",  # Replace with the website to crawl
        max_depth=2,  # Maximum depth to follow links
        max_pages=50,  # Maximum number of pages to crawl
        concurrency=5,  # Number of concurrent worker tasks
        rate_limit=1,  # Rate limit: 0.5 seconds between requests
        polite_crawling=True,  # Enable polite crawling behavior
    )

    # Step 2: Instantiate the crawler
    crawler = Spider(config)

    # Step 3: Initialize the crawler (fetch robots.txt and set up)
    await crawler.initialize()

    # Step 4: Start crawling
    print("Starting the web crawler...")
    visited_urls = await crawler.crawl()

    # Step 5: Display results
    print("\nCrawling complete!")
    print(f"Visited {len(visited_urls)} URLs:")
    for url in visited_urls:
        print(url)


# Step 6: Run the program using trio
if __name__ == "__main__":
    trio.run(main)
