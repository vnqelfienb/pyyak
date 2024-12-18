import urllib.parse
from typing import List, Set, Tuple

from selectolax.parser import HTMLParser


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
        links = set()
        for node in parser.css("a[href]"):
            href = node.attributes.get("href")
            if href:
                absolute_url = urllib.parse.urljoin(base_url, href)
                links.add(absolute_url)  # Use set to avoid duplicates
        return list(links)

    @staticmethod
    def filter_links(
        links: List[str],
        base_url: str,
        visited_urls: Set[str],
        max_depth: int,
        current_depth: int = 0,
    ) -> List[Tuple[str, int]]:
        """
        Filter and prepare links for crawling.

        :param links: List of URLs to filter
        :param base_url: Base URL to constrain crawling
        :param visited_urls: Set of already visited URLs
        :param max_depth: Maximum crawl depth
        :param current_depth: The current crawl depth
        :return: List of (URL, depth) tuples to crawl
        """
        filtered_links = []
        for link in links:
            # Normalize and check link validity
            parsed_url = urllib.parse.urlparse(link)

            if not parsed_url.scheme in ["http", "https"]:  # Skip non-HTTP/HTTPS links
                continue

            # Ensure the link is within the same domain
            if link.startswith(base_url):
                if link not in visited_urls and current_depth < max_depth:
                    filtered_links.append((link, current_depth + 1))  # increment depth
        return filtered_links
