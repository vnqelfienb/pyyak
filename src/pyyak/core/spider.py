import urllib
from typing import Set, Tuple

import httpx
import trio

from .config import SpiderConfig
from .link_extractor import LinkExtractor
from .managers import RobotsTxtManager, UserAgentManager
from .page_fetcher import PageFetcher
from .rate_limiter import RateLimiter


class Spider:
    def __init__(self, config: SpiderConfig):
        self.config = config
        self.user_agent = {"User-Agent": UserAgentManager.get_random_user_agent()}

        # Fetch robots.txt
        self.robots_txt_manager = RobotsTxtManager()

        # Initialize components
        self.rate_limiter = RateLimiter(config)
        self.page_fetcher = PageFetcher(config, self.rate_limiter, self.user_agent)

        # Crawling state
        self.visited_urls: Set[str] = set()
        self.queued_urls: Set[Tuple[str, int]] = set()  # Store (url, depth) tuples
        self.send_channel, self.receive_channel = trio.open_memory_channel(
            config.max_pages
        )
        
        # Initial queue
        initial_url = config.base_url
        self.send_channel.send_nowait((initial_url, 0))
        self.queued_urls.add((initial_url, 0))

        # Synchronization
        self.lock = trio.Lock()
        self.crawler_finished = trio.Event()
        self.disallowed_paths = set()  # Initialize to empty set

    async def initialize(self):
        """
        Initialize the spider by fetching robots.txt
        Handles cases where robots.txt might not exist
        """
        try:
            # Attempt to fetch robots.txt, but don't fail if it's not found
            self.disallowed_paths = await self.robots_txt_manager.fetch_robots_txt(
                self.config.base_url
            )
            print(f"Robots.txt parsed. Disallowed paths: {self.disallowed_paths}")
        except Exception as e:
            print(f"Error fetching robots.txt: {e}")
            # Set disallowed paths to an empty set to allow crawling
            self.disallowed_paths = set()
        return self

    async def crawl_worker(self, client: httpx.AsyncClient):
        try:
            # Convert disallowed paths to regex patterns
            regex_patterns = RobotsTxtManager.convert_to_regex(self.disallowed_paths)

            while True:
                # Check if we've reached max pages or max depth
                if (len(self.visited_urls) >= self.config.max_pages or 
                    not self.queued_urls or 
                    all(depth >= self.config.max_depth for (_, depth) in self.queued_urls)):
                    self.crawler_finished.set()
                    break

                try:
                    # Use a timeout to prevent indefinite blocking
                    with trio.fail_after(1):
                        url, depth = await self.receive_channel.receive()
                except trio.TooSlowError:
                    # If no URLs are available and we're done, exit
                    if self.crawler_finished.is_set():
                        break
                    continue

                # Skip if URL has been visited or depth is too great
                if (url in self.visited_urls or 
                    depth > self.config.max_depth):
                    continue

                # Mark URL as visited
                self.visited_urls.add(url)
                
                # Remove from queued URLs
                self.queued_urls.discard((url, depth))

                print(f"Crawling: {url} (Depth: {depth})")
                html_content = await self.page_fetcher.fetch(client, url)

                if html_content is None:
                    print(f"Failed to fetch {url}. Skipping.")
                    continue

                # Extract links only if we haven't reached max depth
                if depth < self.config.max_depth:
                    try:
                        links = LinkExtractor.extract_links(html_content, url)
                    except Exception as e:
                        print(f"Error extracting links from {url}: {e}")
                        continue

                    # Filter links based on robots.txt and domain rules
                    filtered_links = [
                        link
                        for link in links
                        if not RobotsTxtManager.is_url_disallowed(
                            link, self.config.base_url, regex_patterns
                        )
                        and link.startswith(self.config.base_url)  # Ensure same-domain links
                        and link not in self.visited_urls
                    ]

                    # Send filtered links to the channel
                    for link in filtered_links:
                        try:
                            if (link, depth + 1) not in self.queued_urls:
                                self.send_channel.send_nowait((link, depth + 1))
                                self.queued_urls.add((link, depth + 1))
                        except trio.WouldBlock:
                            break
                        except Exception as e:
                            print(f"Error sending link {link} to channel: {e}")

        except trio.Cancelled:
            print("Worker cancelled.")
        finally:
            self.crawler_finished.set()

    async def crawl(self):
        """
        Start the crawling process.
        """
        # Ensure robots.txt is initialized
        await self.initialize()

        async with httpx.AsyncClient() as client:
            async with trio.open_nursery() as nursery:
                # Start workers
                for _ in range(self.config.concurrency):
                    nursery.start_soon(self.crawl_worker, client)

                try:
                    # Wait for the crawler to finish or timeout
                    with trio.fail_after(60):  # 60-second overall timeout
                        await self.crawler_finished.wait()
                except trio.TooSlowError:
                    print("Crawler timed out.")
                finally:
                    # Signal the workers to stop and close channels
                    nursery.cancel_scope.cancel()
                    await self.send_channel.aclose()

        return self.visited_urls
