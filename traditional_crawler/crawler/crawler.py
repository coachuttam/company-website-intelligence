import time
from collections import deque
from urllib.parse import urlparse, urlunparse

from crawler.fetcher import fetch_page
from crawler.parser import extract_links
from crawler.robots import create_robots_parser


def normalize_url(url: str) -> str:
    parsed = urlparse(url)

    normalized = parsed._replace(fragment="")

    return urlunparse(normalized)


def crawl(
    start_url: str,
    max_pages: int = 10,
    max_depth: int = 1,
    delay: float = 1.0
) -> list[str]:

    queue = deque([(start_url, 0)])
    visited = set()

    start_domain = urlparse(start_url).netloc

    robots = create_robots_parser(start_url)

    while queue and len(visited) < max_pages:

        url, depth = queue.popleft()

        url = normalize_url(url)

        if url in visited:
            continue

        if not robots.can_fetch("*", url):
            print(f"Blocked by robots.txt: {url}")
            continue

        print(f"Crawling: {url} | Depth: {depth}")

        time.sleep(delay)

        html = fetch_page(url)

        links = extract_links(html, url)

        visited.add(url)

        if depth >= max_depth:
            continue

        for link in links:

            link = normalize_url(link)

            link_domain = urlparse(link).netloc

            if link_domain == start_domain and link not in visited:
                queue.append((link, depth + 1))

    return list(visited)