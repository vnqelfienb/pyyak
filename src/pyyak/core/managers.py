import random
import re
import urllib.parse

import httpx


class RobotsTxtManager:
    """
    Manages robots.txt fetching and parsing.
    """

    @staticmethod
    def normalize_path(path: str) -> str:
        """
        Normalize a URL path by stripping trailing slashes and converting to lowercase.
        """
        return path.rstrip("/").lower()

    @staticmethod
    async def fetch_robots_txt(base_url: str) -> set:
        """
        Fetch and parse the robots.txt file from the base URL.

        :param base_url: Base URL of the target site
        :return: A set of disallowed paths for User-agent: *
        """
        robots_txt_url = urllib.parse.urljoin(base_url, "robots.txt")
        headers = {"User-Agent": UserAgentManager.get_random_user_agent()}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(robots_txt_url, headers=headers)

                if response.status_code == 404:
                    print("robots.txt not found (404).")
                    return set()

                response.raise_for_status()
                return RobotsTxtManager.parse_robots_txt(response.text)

        except httpx.HTTPStatusError as e:
            print(f"HTTP error while fetching robots.txt: {e}")
            return set()
        except httpx.RequestError as e:
            print(f"Request error while fetching robots.txt: {e}")
            return set()

    @staticmethod
    def parse_robots_txt(content: str) -> set:
        """
        Parse the robots.txt content and extract disallowed paths for User-agent: *.

        :param content: The robots.txt content as a string
        :return: A set of disallowed paths
        """
        disallowed_paths = set()
        lines = content.splitlines()
        capture_rules = False

        for line in lines:
            line = line.strip()

            if not line or line.startswith("#"):  # Skip comments and empty lines
                continue

            if line.lower().startswith("user-agent:"):
                user_agent = line.split(":", 1)[1].strip()
                capture_rules = user_agent == "*"

            elif capture_rules and line.lower().startswith("disallow:"):
                path = line.split(":", 1)[1].strip()
                if not path:  # Disallow: (empty) means "allow all"
                    continue
                if path == "/":  # Disallow: / means entire site
                    return {"/"}  # Shortcut: block everything
                disallowed_paths.add(RobotsTxtManager.normalize_path(path))

        return disallowed_paths

    @staticmethod
    def convert_to_regex(disallowed_paths: set) -> list:
        """
        Convert disallowed paths into regular expressions.

        :param disallowed_paths: A set of disallowed paths from robots.txt
        :return: A list of compiled regex patterns
        """
        regex_patterns = []
        for path in disallowed_paths:
            # Escape regex special characters, then replace '*' with '.*' for wildcard matching
            path_regex = re.escape(path).replace(r"\*", r".*")
            regex_patterns.append(re.compile(f"^{path_regex}"))
        return regex_patterns

    @staticmethod
    def is_url_disallowed(url: str, base_url: str, regex_patterns: list) -> bool:
        """
        Check if a given URL is disallowed by robots.txt.

        :param url: The full URL to check
        :param base_url: The base URL of the website
        :param regex_patterns: A list of compiled regex patterns
        :return: True if the URL is disallowed, False otherwise
        """
        parsed_url = urllib.parse.urlparse(url)
        full_path = RobotsTxtManager.normalize_path(parsed_url.path)

        for pattern in regex_patterns:
            if pattern.match(full_path):
                return True
        return False


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

    @classmethod
    def load_custom_user_agents(cls, path: str | None):
        """
        Load custom user agents from a file.

        :param path: The path to the file containing custom user agents
        :return: A list of custom user agents
        """
        custom_user_agents = cls.DEFAULT_USER_AGENTS.copy()

        if path:
            try:
                with open(path, "r") as file:
                    user_agents = file.readlines()
                    custom_user_agents.extend(
                        line.strip() for line in user_agents if line.strip()
                    )
            except FileNotFoundError:
                print(f"User-agent file not found at: {path}")
            except Exception as e:
                print(f"Error reading user-agent file: {e}")

        return custom_user_agents
