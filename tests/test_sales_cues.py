"""Tests for wi.crawl.sales_cues (B-61). Pure and offline."""
from wi.crawl.sales_cues import extract_cta_lines, find_sales_cues, is_pricing_page_url

PAGE = "\n".join([
    "Free",
    "$0 per member / month",
    "Get Notion free",
    "Plus",
    "$10 per member / month",
    "Try Plus",
    "Enterprise",
    "Custom pricing",
    "Contact sales",
    "Questions? We read every message.",
])


def test_finds_both_kinds_on_a_typical_pricing_page():
    cues = find_sales_cues(PAGE)
    assert "Get Notion free" in cues.self_serve
    assert "Contact sales" in cues.contact_sales
    assert "Custom pricing" in cues.contact_sales
    assert cues.hybrid


def test_returns_lines_exactly_as_they_appear():
    cues = find_sales_cues("   Start for free  \nTalk to sales")
    assert cues.self_serve == ["Start for free"]
    assert cues.contact_sales == ["Talk to sales"]


def test_self_serve_only_page_is_not_hybrid():
    cues = find_sales_cues("Starter\n$29/month\nStart Free Trial")
    assert cues.self_serve == ["Start Free Trial"] and cues.contact_sales == []
    assert not cues.hybrid


def test_contact_only_page_is_not_hybrid():
    cues = find_sales_cues("Request a demo\nGet in touch")
    assert cues.self_serve == [] and len(cues.contact_sales) == 2
    assert not cues.hybrid


def test_long_sentences_are_ignored():
    long_line = ("If you have any questions about this privacy policy you can contact us at any time "
                 "using the details below and we will reply as soon as we can.")
    assert len(long_line) > 120
    assert find_sales_cues(long_line).contact_sales == []


def test_a_line_matching_both_kinds_counts_as_contact_sales_only():
    cues = find_sales_cues("Contact sales to get started")
    assert cues.contact_sales == ["Contact sales to get started"] and cues.self_serve == []


def test_ordinary_text_has_no_cues():
    cues = find_sales_cues("The most ambitious companies run on us.\nTrusted by teams that ship.")
    assert cues.self_serve == [] and cues.contact_sales == []


def test_duplicates_and_cap_per_kind():
    cues = find_sales_cues("\n".join(["Contact sales"] * 3 + ["Talk to sales", "Book a demo", "Get in touch"]),
                           max_per_kind=2)
    assert cues.contact_sales == ["Contact sales", "Talk to sales"]


def test_curly_apostrophe_in_lets_talk():
    assert find_sales_cues("Let’s talk").contact_sales == ["Let’s talk"]


def test_is_pricing_page_url():
    assert is_pricing_page_url("https://x.example/en/pricing-options")
    assert is_pricing_page_url("https://x.example/plans")
    assert not is_pricing_page_url("https://x.example/customers/openai")
    assert not is_pricing_page_url("https://pricing.example/")   # host name alone does not count


def test_extract_cta_lines_reads_button_and_link_labels_in_order():
    html = (
        "<html><body><nav><a href='/'>Home</a></nav>"
        "<h1>Pricing</h1>"
        "<a class='btn' href='/signup'>Get Notion free</a>"
        "<button>Contact   sales</button>"
        "<input type='submit' value='Request a demo'>"
        "<input type='text' value='not a button'>"
        "<a href='/card'>" + "x" * 80 + "</a>"
        "<a href='/signup2'>Get Notion free</a>"
        "</body></html>"
    )
    assert extract_cta_lines(html) == ["Home", "Get Notion free", "Contact sales", "Request a demo"]


def test_cta_lines_feed_the_cue_finder():
    html = "<a href='/s'>Start for free</a><a href='/c'>Talk to sales</a><a href='/x'>Blog</a>"
    cues = find_sales_cues("\n".join(extract_cta_lines(html)))
    assert cues.self_serve == ["Start for free"] and cues.contact_sales == ["Talk to sales"]
