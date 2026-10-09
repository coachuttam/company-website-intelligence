"""B-88: a per-run snapshot of what the crawl fetched and what the model was shown.

Run JSONs keep claims and crawl diagnostics but never the page text, so a later question such as
"did the site change, or did the model?" (the post-B-87 dev drop) or "was this quote really on the
cleaned page?" (the Postman spot-check) could not be answered from saved files. This writes, for
every run, one JSON file under data/clean/<slug>/ (git-ignored) holding each fetched page's fetch
metadata (status, timing, redirect, JS render, raw size and sha256) and, for pages that were
cleaned, the cleaned title and text with its sha256 and whether it was sent to the model.

It only records: nothing here changes what is crawled, cleaned, sent or extracted.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional


def sha256_text(text: Optional[str]) -> Optional[str]:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text is not None else None


def build_snapshot(site_url: str, retrieved_at: str, fetched: Iterable, cleaned: Iterable,
                   sent_urls: Iterable[str]) -> Dict:
    """`fetched` are wi.crawl.fetch.FetchResult objects, `cleaned` wi.crawl.clean.CleanPage
    objects, `sent_urls` the cleaned pages actually sent to the model."""
    clean_by_url = {cp.url: cp for cp in cleaned}
    sent = set(sent_urls)
    pages: List[Dict] = []
    for p in fetched:
        entry = {
            "url": p.url, "requested_url": p.requested_url, "status": p.status,
            "status_code": p.status_code, "error_code": p.error_code, "error": p.error,
            "elapsed_s": round(p.elapsed_s, 3), "js_rendered": p.js_rendered,
            "raw_truncated": p.truncated,
            "raw_chars": len(p.html) if p.html else 0, "raw_sha256": sha256_text(p.html),
        }
        cp = clean_by_url.get(p.url)
        if cp is not None:
            entry.update({"clean_title": cp.title, "clean_text": cp.text,
                          "clean_chars": len(cp.text), "clean_truncated": cp.truncated,
                          "clean_sha256": sha256_text(cp.text), "sent_to_model": cp.url in sent})
        pages.append(entry)
    return {"site_url": site_url, "retrieved_at": retrieved_at, "pages": pages}


def write_snapshot(root: Path, slug: str, snapshot: Dict, now: Optional[datetime] = None) -> Dict:
    """Writes the snapshot to <root>/data/clean/<slug>/<YYYYMMDD-HHMMSS>.json and returns
    {"path": <path relative to root>, "sha256": <sha256 of the file's bytes>, "pages": n}."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    out_dir = Path(root) / "data" / "clean" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stamp}.json"
    data = json.dumps(snapshot, ensure_ascii=False, indent=1).encode("utf-8")
    path.write_bytes(data)
    return {"path": str(path.relative_to(root)), "sha256": hashlib.sha256(data).hexdigest(),
            "pages": len(snapshot["pages"])}
