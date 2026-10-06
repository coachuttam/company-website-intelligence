from bs4 import BeautifulSoup
from urllib.parse import urljoin


def extract_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")

    links = set()

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()

        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue

        absolute_url = urljoin(base_url, href)

        links.add(absolute_url)

    return list(links)