import time
import urllib.parse
from typing import Dict, List

import trio

from .config import SpiderConfig


class RateLimiter:
    """
    Manages rate limiting for web crawling.
    """

    def __init__(self, config: SpiderConfig):
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

