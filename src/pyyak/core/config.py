from typing import Optional

from pydantic import BaseModel, HttpUrl


class RobotsTxtConfig(BaseModel):
    base_url: HttpUrl

class SpiderConfig(BaseModel):
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

