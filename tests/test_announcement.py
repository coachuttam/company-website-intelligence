"""Announcement contract tests (B-07 / OUT-04). Maps to Final PRD Section 4 Group E and Section
5 OUT-04: "Capture company-reported announcements only as dated first-party items, never as core
fields."
"""
import pytest
from pydantic import ValidationError

from wi.schemas.announcement import Announcement

GOOD = dict(
    announcement_id="a001",
    text="$5M Series A funding round",
    category="funding",
    date="March 2025",
    source_url="https://northledger.example/newsroom/series-a",
    evidence="We're thrilled to announce our $5M Series A funding round, closed in March 2025.",
    retrieved_at="2026-09-27",
)


def test_valid_announcement_passes():
    ann = Announcement(**GOOD)
    assert ann.category == "funding"
    assert ann.date == "March 2025"


@pytest.mark.parametrize("missing", ["text", "category", "date", "source_url", "evidence", "retrieved_at"])
def test_announcement_missing_a_required_field_fails(missing):
    data = {**GOOD}
    data.pop(missing)
    with pytest.raises(ValidationError):
        Announcement(**data)


def test_announcement_with_unknown_category_fails():
    with pytest.raises(ValidationError):
        Announcement(**{**GOOD, "category": "gossip"})


@pytest.mark.parametrize("category", [
    "funding", "product_launch", "partnership", "expansion",
    "leadership_change", "acquisition", "other",
])
def test_every_known_category_passes(category):
    assert Announcement(**{**GOOD, "category": category}).category == category


def test_page_title_is_optional():
    ann = Announcement(**GOOD)
    assert ann.page_title is None
    ann2 = Announcement(**{**GOOD, "page_title": "Newsroom"})
    assert ann2.page_title == "Newsroom"
