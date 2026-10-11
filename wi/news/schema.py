"""The canonical news object (PRD Section 8) and the per-company report around it (B-104)."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, model_validator

LOOKBACK_DAYS = 90          # PRD Section 13: 90-day lookback
MAX_ITEMS = 10              # at most 10 de-duplicated items
SOURCE_TIMEOUT_S = 15.0     # per source
TOTAL_BUDGET_S = 60.0       # per company

SourceClass = Literal["company_announcement", "third_party_news"]
EventType = Literal["funding", "product_launch", "partnership", "customer_contract", "leadership_change",
                    "expansion", "acquisition", "hiring_layoffs", "legal_regulatory", "other"]


class NewsItem(BaseModel):
    news_id: str
    company_id: str
    source_class: SourceClass           # never "first_party" or "verified" (R-NEWS-002, B-25)
    publisher: str
    url: str
    headline: str
    published_at: str
    retrieved_at: str
    evidence: Optional[str] = None      # the feed's own summary text; None only when inaccessible
    event_type: EventType
    relevance_status: Literal["matched", "inaccessible"]
    note: Optional[str] = None

    @model_validator(mode="after")
    def _evidence_or_inaccessible(self):
        if self.relevance_status == "matched" and not self.evidence:
            raise ValueError("a matched item needs evidence; otherwise mark it inaccessible (R-NEWS-005)")
        return self


class NewsReport(BaseModel):
    company_id: str
    company_name: str
    domain: str
    status: Literal["ok", "not_found", "unavailable"]
    reason: Optional[str] = None
    lookback_days: int = LOOKBACK_DAYS
    retrieved_at: str
    items: List[NewsItem] = []
    sources: List[dict] = []            # every page/feed tried: {url, kind, status, reason}
    record: dict = {}                   # latency, model calls, tokens, cost, counts (AC-12)
