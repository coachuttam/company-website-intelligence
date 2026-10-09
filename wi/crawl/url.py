"""URL validation (INP-01, INP-02 first half). No network calls happen here.

Redirect following and robots.txt come later (Week 2, Day 6); this module only decides
whether the input is a plausible public company URL and what the approved domains are.
"""
from __future__ import annotations

import ipaddress
import re
from typing import List, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel

# Restricted platforms are out of scope (PRD Section 2).
RESTRICTED_HOSTS = {
    "linkedin.com", "x.com", "twitter.com", "facebook.com", "instagram.com",
    "tiktok.com", "youtube.com", "reddit.com",
}

_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


class UrlResult(BaseModel):
    status: str                          # "ok" | "error"
    error_code: Optional[str] = None     # INVALID_URL | RESTRICTED_PLATFORM
    message: Optional[str] = None
    url: Optional[str] = None            # normalised URL
    approved_domains: List[str] = []     # canonical host plus its www / apex variant


RESTRICTED_MESSAGE = "Restricted platform. Provide the company's own website."


def is_restricted_host(host: str) -> bool:
    """True for a restricted platform (or a subdomain of one), with or without "www.". Shared by
    validate_company_url() and the crawl's start-page redirect check (B-86), so both use one rule."""
    host = (host or "").lower().rstrip(".")
    apex = host[4:] if host.startswith("www.") else host
    return apex in RESTRICTED_HOSTS or any(apex.endswith("." + r) for r in RESTRICTED_HOSTS)


def _error(code: str, message: str) -> UrlResult:
    return UrlResult(status="error", error_code=code, message=message)


def validate_company_url(raw: object) -> UrlResult:
    if not isinstance(raw, str) or not raw.strip():
        return _error("INVALID_URL", "Invalid company URL")

    text = raw.strip()
    if any(ch.isspace() for ch in text):
        return _error("INVALID_URL", "Invalid company URL")

    # Add a scheme when the input looks like a bare domain.
    if "://" not in text:
        text = "https://" + text

    try:
        parts = urlsplit(text)
        host = (parts.hostname or "").lower().rstrip(".")
    except ValueError:
        return _error("INVALID_URL", "Invalid company URL")

    if parts.scheme not in ("http", "https") or not host:
        return _error("INVALID_URL", "Invalid company URL")

    # Reject IP addresses and localhost: not a public company site.
    try:
        ipaddress.ip_address(host)
        return _error("INVALID_URL", "Invalid company URL")
    except ValueError:
        pass
    if not _HOST_RE.match(host):
        return _error("INVALID_URL", "Invalid company URL")

    apex = host[4:] if host.startswith("www.") else host
    if is_restricted_host(host):
        return _error("RESTRICTED_PLATFORM", RESTRICTED_MESSAGE)

    path = parts.path or "/"
    normalised = f"{parts.scheme}://{host}{path}"
    return UrlResult(
        status="ok",
        url=normalised,
        approved_domains=sorted({apex, "www." + apex}),
    )
