from typing import Optional

import httpx

from .config import SpiderConfig
from .managers import UserAgentManager
from .rate_limiter import RateLimiter


class PageFetcher:
    """
    Handles HTTP requests and page fetching with advanced header management.
    """

    def __init__(
        self,
        config: SpiderConfig,
        rate_limiter: RateLimiter,
        user_agent: UserAgentManager,
    ):
        self.config = config
        self.rate_limiter = rate_limiter
        self.user_agent = UserAgentManager.get_random_user_agent()

    async def fetch(self, client: httpx.AsyncClient, url: str) -> Optional[str]:
        """
        Fetch page content with rate limiting and custom headers.
        Explicitly disable redirects.

        :param client: HTTP client
        :param url: URL to fetch
        :return: Page content or None
        """
        # Apply rate limiting
        await self.rate_limiter.wait(url)

        # Generate headers
        headers = {"User-Agent": self.user_agent}

        try:
            # Disable redirects and set a strict timeout
            response = await client.get(
                url,
                headers=headers,
                follow_redirects=False,  # Explicitly disable redirects
                timeout=httpx.Timeout(10.0, connect=5.0),  # More granular timeout
            )

            # Check if the response is a redirect
            if response.status_code in (301, 302, 303, 307, 308):
                print(f"Redirect encountered for {url}: {response.status_code}")
                return None

            response.raise_for_status()
            return response.text
        except httpx.RequestError as e:
            print(f"Request failed for {url}: {e}")
            return None
        except httpx.HTTPStatusError as e:
            print(f"HTTP error for {url}: {e}")
            return None
