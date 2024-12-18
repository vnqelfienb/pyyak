import random
import httpx
import trio
from selectolax.parser import HTMLParser
import urllib.parse
import time
import logging
from dataclasses import dataclass, field
from typing import Set, Dict, List, Optional, Tuple


class RobotsTxtManager:
    """
    Manages robots.txt fetching and parsing.
    """

    @staticmethod
    async def fetch_robots_txt(base_url: str) -> dict:
        """
        Fetch and parse the robots.txt file from the base URL.

        :param base_url: Base URL of the target site
        :return: A dictionary containing disallowed paths
        """
        robots_txt_url = urllib.parse.urljoin(base_url, "robots.txt")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(robots_txt_url)
                response.raise_for_status()
                return RobotsTxtManager.parse_robots_txt(response.text)
        except httpx.RequestError as e:
            print(f"Error fetching robots.txt: {e}")
            return {}

    @staticmethod
    def parse_robots_txt(content: str) -> dict:
        """
        Parse the robots.txt content and extract disallowed paths.

        :param content: The robots.txt content as a string
        :return: Dictionary of disallowed paths
        """
        disallowed_paths = {}
        lines = content.split("\n")
        current_user_agent = "default"
        for line in lines:
            line = line.strip()
            if line.startswith("User-agent:"):
                current_user_agent = line.split(":", 1)[1].strip()
            elif line.startswith("Disallow:"):
                path = line.split(":", 1)[1].strip()
                disallowed_paths.setdefault(current_user_agent, []).append(path)

        return disallowed_paths


# Example of using RobotsTxtManager in an async context
async def example_usage(base_url: str):
    robots_txt_manager = RobotsTxtManager()
    disallowed_paths = await robots_txt_manager.fetch_robots_txt(base_url)
    print(disallowed_paths)


class RobotsTxtFilter:
    """
    Filters URLs based on robots.txt disallow rules.
    """

    @staticmethod
    def filter_urls(
        urls: List[str], disallowed_paths: dict, user_agent: str, base_url: str
    ) -> List[str]:
        """
        Filter out URLs that are disallowed by robots.txt rules.

        :param urls: List of URLs to filter
        :param disallowed_paths: Disallowed paths from robots.txt
        :param user_agent: User agent string for checking
        :param base_url: Base URL to use for filtering
        :return: List of allowed URLs
        """
        allowed_urls = []
        for url in urls:
            parsed_url = urllib.parse.urlparse(url)
            # Filter by disallowed paths
            disallowed = any(
                parsed_url.path.startswith(disallowed_path)
                for disallowed_path in disallowed_paths.get(user_agent, [])
            )
            if not disallowed:
                allowed_urls.append(url)
        return allowed_urls


# User Agent Management
class UserAgentManager:
    """
    Manages user agent rotation and selection.
    """

    DEFAULT_USER_AGENTS = [
        # Chrome on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        # Firefox on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
        # Safari on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
        # Edge on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59",
    ]

    @classmethod
    def get_random_user_agent(cls) -> str:
        """
        Select a random user agent.

        :return: A randomly selected user agent string
        """
        return random.choice(cls.DEFAULT_USER_AGENTS)


# Header Management
@dataclass
class HeaderConfig:
    """
    Configuration for HTTP request headers.
    """

    base_headers: Dict[str, str] = field(
        default_factory=lambda: {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Dnt": "1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
        }
    )
    user_agent_rotation: bool = True
    custom_headers: Dict[str, str] = field(default_factory=dict)

    def generate_headers(self) -> Dict[str, str]:
        """
        Generate headers for a request.

        :return: Dictionary of headers
        """
        # Start with base headers
        headers = self.base_headers.copy()

        # Add custom headers (can override base headers)
        headers.update(self.custom_headers)

        # Optionally rotate user agent
        if self.user_agent_rotation:
            headers["User-Agent"] = UserAgentManager.get_random_user_agent()

        return headers


# Configuration Management
@dataclass
class CrawlerConfig:
    """
    Configuration container for web crawling parameters.
    """

    base_url: str
    max_depth: int = 2
    max_pages: int = 100
    concurrency: int = 10
    rate_limit: Optional[float] = None
    domain_rate_limit: Optional[float] = None
    min_delay: float = 0
    polite_crawling: bool = True
    logger: Optional[logging.Logger] = None
    header_config: HeaderConfig = field(default_factory=HeaderConfig)


# Rate Limiting Management
class RateLimiter:
    """
    Manages rate limiting for web crawling.
    """

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self.domain_last_request: Dict[str, float] = {}
        self.global_request_times: List[float] = []
        self.lock = trio.Lock()

    async def wait(self, url: str) -> float:
        """
        Apply rate limiting before making a request.

        :param url: URL to be requested
        :return: Time waited before request
        """
        current_time = time.time()
        wait_time = 0
        domain = urllib.parse.urlparse(url).netloc

        async with self.lock:
            # Domain-specific rate limiting
            if self.config.domain_rate_limit:
                last_request = self.domain_last_request.get(domain, 0)
                domain_wait = max(
                    0,
                    (1 / self.config.domain_rate_limit) - (current_time - last_request),
                )
                wait_time = max(wait_time, domain_wait)

            # Global rate limiting
            if self.config.rate_limit:
                # Remove old request times
                self.global_request_times = [
                    t for t in self.global_request_times if current_time - t < 1
                ]

                # Check if we've exceeded global rate limit
                if len(self.global_request_times) >= self.config.rate_limit:
                    wait_time = max(wait_time, 1)

                # Record this request time
                self.global_request_times.append(current_time)

            # Minimum delay between requests
            if self.config.min_delay > 0:
                last_request = self.domain_last_request.get(domain, 0)
                min_delay_wait = max(
                    0, self.config.min_delay - (current_time - last_request)
                )
                wait_time = max(wait_time, min_delay_wait)

            # Update last request time for this domain
            self.domain_last_request[domain] = current_time

        # Wait if necessary
        if wait_time > 0:
            await trio.sleep(wait_time)

        return wait_time


# Link Extraction and Filtering
class LinkExtractor:
    """
    Handles link extraction and filtering.
    """

    @staticmethod
    def extract_links(html_content: str, base_url: str) -> List[str]:
        """
        Extract and normalize links from HTML content.

        :param html_content: HTML content to parse
        :param base_url: Base URL for resolving relative links
        :return: List of absolute, normalized URLs
        """
        parser = HTMLParser(html_content)
        links = []
        for node in parser.css("a[href]"):
            href = node.attributes.get("href")
            if href:
                # Use urllib.parse for robust URL joining
                absolute_url = urllib.parse.urljoin(base_url, href)
                # Basic filtering
                links.append(absolute_url)
        return links

    @staticmethod
    def filter_links(
        links: List[str], base_url: str, visited_urls: Set[str], max_depth: int
    ) -> List[Tuple[str, int]]:
        """
        Filter and prepare links for crawling.

        :param links: List of URLs to filter
        :param base_url: Base URL to constrain crawling
        :param visited_urls: Set of already visited URLs
        :param max_depth: Maximum crawl depth
        :return: List of (URL, depth) tuples to crawl
        """
        filtered_links = []
        for link in links:
            # Constrain to base domain
            if link.startswith(base_url):
                # Avoid revisiting
                if link not in visited_urls:
                    filtered_links.append((link, 0))  # depth will be set by crawler
        return filtered_links


class PageFetcher:
    """
    Handles HTTP requests and page fetching with advanced header management.
    """

    def __init__(self, config: CrawlerConfig, rate_limiter: "RateLimiter"):
        self.config = config
        self.rate_limiter = rate_limiter
        self.logger = config.logger or logging.getLogger(__name__)
        self.header_config = config.header_config

    async def fetch(self, client: httpx.AsyncClient, url: str) -> Optional[str]:
        """
        Fetch page content with rate limiting and custom headers.

        :param client: HTTP client
        :param url: URL to fetch
        :return: Page content or None
        """
        # Apply rate limiting
        await self.rate_limiter.wait(url)

        # Generate headers
        headers = self.header_config.generate_headers()

        try:
            response = await client.get(url, timeout=10, headers=headers)
            response.raise_for_status()
            return response.text
        except httpx.RequestError as e:
            self.logger.error(f"Request failed for {url}: {e}")
            return None


# Web Crawler
class WebCrawler:
    def __init__(self, config: CrawlerConfig):
        self.config = config

        # Fetch robots.txt
        self.robots_txt_manager = RobotsTxtManager()
        self.disallowed_paths = await self.robots_txt_manager.fetch_robots_txt(
            config.base_url
        )

        # Initialize components
        self.rate_limiter = RateLimiter(config)
        self.page_fetcher = PageFetcher(config, self.rate_limiter)

        # Crawling state
        self.visited_urls: Set[str] = set()
        self.send_channel, self.receive_channel = trio.open_memory_channel(
            config.max_pages
        )
        self.send_channel.send_nowait((config.base_url, 0))

        # Synchronization
        self.lock = trio.Lock()
        self.crawler_finished = trio.Event()

        # Logging
        self.logger = config.logger or logging.getLogger(__name__)

    async def crawl_worker(self, client: httpx.AsyncClient):
        try:
            while True:
                try:
                    with trio.fail_after(1):
                        url, depth = await self.receive_channel.receive()
                except trio.TooSlowError:
                    if self.crawler_finished.is_set():
                        return
                    continue

                async with self.lock:
                    if (
                        url in self.visited_urls
                        or depth > self.config.max_depth
                        or len(self.visited_urls) >= self.config.max_pages
                    ):
                        if len(self.visited_urls) >= self.config.max_pages:
                            self.crawler_finished.set()
                        continue

                    self.visited_urls.add(url)

                self.logger.info(f"Crawling: {url} (Depth: {depth})")
                html_content = await self.page_fetcher.fetch(client, url)

                if html_content is None:
                    continue

                # Extract and queue new links
                if depth < self.config.max_depth:
                    links = LinkExtractor.extract_links(html_content, url)
                    allowed_links = RobotsTxtFilter.filter_urls(
                        links,
                        self.disallowed_paths,
                        self.header_config.base_headers["User-Agent"],
                        self.config.base_url,
                    )
                    filtered_links = LinkExtractor.filter_links(
                        allowed_links,
                        self.config.base_url,
                        self.visited_urls,
                        self.config.max_depth,
                    )

                    async with self.lock:
                        for link, _ in filtered_links:
                            try:
                                self.send_channel.send_nowait((link, depth + 1))
                            except trio.WouldBlock:
                                break

        except trio.Cancelled:
            return

    async def crawl(self):
        """
        Start the crawling process.
        """
        async with httpx.AsyncClient() as client:
            async with trio.open_nursery() as nursery:
                # Start crawler workers
                for _ in range(self.config.concurrency):
                    nursery.start_soon(self.crawl_worker, client)

                # Wait for crawling to complete
                await self.crawler_finished.wait()

                # Close the send channel
                await self.send_channel.aclose()

                # Cancel any remaining workers
                nursery.cancel_scope.cancel()

        return self.visited_urls


# Example usage with enhanced header configuration
def setup_logging():
    """
    Set up logging configuration.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return logging.getLogger(__name__)


# Main execution
if __name__ == "__main__":

    async def main():
        # Configure logging
        logger = setup_logging()

        # Create custom header configuration
        header_config = HeaderConfig(
            base_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
            user_agent_rotation=True,  # Enable user agent rotation
            custom_headers={
                "X-Crawler-Version": "1.0",  # Custom header
                "Referer": "https://example.com",  # Example referrer
            },
        )

        # Create crawler configuration with custom headers
        config = CrawlerConfig(
            base_url="https://www.alo.bg/",
            max_depth=5,
            max_pages=500,
            concurrency=10,
            rate_limit=2,  # 2 requests per second globally
            domain_rate_limit=1,  # 1 request per second per domain
            min_delay=1,  # Minimum 0.5 seconds between requests
            logger=logger,
            header_config=header_config,
        )

        # Create and run crawler
        crawler = WebCrawler(config)
        visited_urls = await crawler.crawl()

        # Print results
        print("Visited URLs:")
        for url in sorted(visited_urls):
            print(url)

    trio.run(main)
