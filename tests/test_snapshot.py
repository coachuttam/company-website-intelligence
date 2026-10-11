"""B-88: per-run snapshot of fetched pages and cleaned text, with checksums, under data/clean/."""
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from wi.crawl.clean import CleanPage
from wi.crawl.fetch import FetchResult
from wi.crawl.snapshot import build_snapshot, sha256_text, write_snapshot

ROOT = Path(__file__).resolve().parent.parent


def _pages():
    fetched = [
        FetchResult(url="https://acme.test/", status="ok", status_code=200,
                    html="<html><body>Hello</body></html>", elapsed_s=0.4321),
        FetchResult(url="https://acme.test/about", status="ok", status_code=200,
                    html="<html><body>About</body></html>", elapsed_s=1.2,
                    requested_url="https://acme.test/old-about"),
        FetchResult(url="https://acme.test/private", status="error", status_code=403,
                    error_code="BLOCKED", error="HTTP 403", elapsed_s=0.1),
    ]
    cleaned = [CleanPage(url="https://acme.test/", title="Acme", text="Hello"),
               CleanPage(url="https://acme.test/about", title="About", text="About")]
    return fetched, cleaned


def test_b88_snapshot_holds_fetch_metadata_clean_text_and_checksums():
    fetched, cleaned = _pages()
    snap = build_snapshot("https://acme.test/", "2026-10-09", fetched, cleaned, ["https://acme.test/"])
    home, about, private = snap["pages"]
    assert home["clean_text"] == "Hello" and home["clean_sha256"] == sha256_text("Hello")
    assert home["raw_sha256"] == sha256_text(fetched[0].html) and home["elapsed_s"] == 0.432
    assert home["sent_to_model"] is True and about["sent_to_model"] is False   # e.g. dropped by budget
    assert about["requested_url"] == "https://acme.test/old-about"
    assert private["error_code"] == "BLOCKED" and "clean_text" not in private and private["raw_sha256"] is None


def test_b88_write_snapshot_returns_a_path_and_a_checksum_of_the_file(tmp_path):
    fetched, cleaned = _pages()
    snap = build_snapshot("https://acme.test/", "2026-10-09", fetched, cleaned, [])
    ref = write_snapshot(tmp_path, "acme_test", snap, now=datetime(2026, 10, 9, 13, 5, 7))
    assert ref["path"] == "data/clean/acme_test/20261009-130507.json" and ref["pages"] == 3
    data = (tmp_path / ref["path"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == ref["sha256"]
    assert json.loads(data)["pages"][0]["clean_text"] == "Hello"


def _inside_git_work_tree() -> bool:
    try:
        out = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT, capture_output=True, text=True)
    except OSError:
        return False
    return out.returncode == 0 and out.stdout.strip() == "true"


@pytest.mark.skipif(not _inside_git_work_tree(), reason="needs a git work tree (e.g. not an unzipped archive)")
def test_b88_snapshots_are_git_ignored():
    out = subprocess.run(["git", "check-ignore", "-q", "data/clean/acme_test/20261009-130507.json"],
                         cwd=ROOT, capture_output=True)
    assert out.returncode == 0
