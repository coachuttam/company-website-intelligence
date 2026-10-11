"""Who the news is about (B-104): the company name and canonical domain from a saved run, and the
domain rule that decides whether a URL belongs to the company (entity match for company-own sources)."""
from __future__ import annotations

from typing import NamedTuple, Optional
from urllib.parse import urlsplit


class Company(NamedTuple):
    company_id: str
    name: str
    domain: str        # apex host, no "www."
    home_url: str


def apex(host: str) -> str:
    host = (host or "").lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def belongs_to(url: str, domain: str) -> bool:
    """True when the URL's host is the company's domain or one of its subdomains."""
    host = apex(urlsplit(url).hostname or "")
    return host == domain or host.endswith("." + domain)


def company_from_run(run: dict) -> Optional[Company]:
    pages = (run.get("crawl") or {}).get("pages") or []
    home = (run.get("crawl") or {}).get("final_url") or (pages[0]["url"] if pages else None)
    if not home:
        return None
    domain = apex(urlsplit(home).hostname or "")
    name = next((c.get("value") for c in run.get("claims", [])
                 if c.get("field") == "company_identity.name" and c.get("status") != "not_found"), None)
    return Company(company_id=domain.replace(".", "_"), name=name or domain.split(".")[0].title(),
                   domain=domain, home_url=f"{urlsplit(home).scheme}://{urlsplit(home).netloc}/")
