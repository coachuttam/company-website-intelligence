"""Tests for wi.crawl.clean."""
from __future__ import annotations

import wi.crawl.clean as clean_module
from wi.crawl.clean import clean_page, is_priority_url, resolve_char_cap

RICH_HTML = """
<html>
<head><title>Basecamp -- Project management</title></head>
<body>
<nav>Home About Pricing</nav>
<header>Top banner</header>
<main>
  <h1>Basecamp is project management without all the nonsense.</h1>
  <p>Rock solid and famously easy to use. Start a 30-day free trial today.</p>
</main>
<footer>Copyright 2026</footer>
</body>
</html>
"""

SPARSE_HTML = "<html><head></head><body><div>Just some text with no structure.</div></body></html>"


def test_clean_page_extracts_title_and_strips_nav_footer():
    page = clean_page("https://example.com/", RICH_HTML, max_clean_chars=12000)
    assert page.title == "Basecamp -- Project management"
    assert "free trial" in page.text.lower()
    assert "Copyright 2026" not in page.text
    assert page.truncated is False


def test_clean_page_falls_back_when_trafilatura_finds_nothing():
    page = clean_page("https://example.com/sparse", SPARSE_HTML, max_clean_chars=12000)
    assert "Just some text" in page.text


def test_clean_page_truncates_at_max_clean_chars():
    html = "<html><body><p>" + ("word " * 5000) + "</p></body></html>"
    page = clean_page("https://example.com/long", html, max_clean_chars=100)
    assert len(page.text) <= 100
    assert page.truncated is True


# --- Always keep the page's <h1> (decided 2026-09-24) -----------------------------------------
# Real bug found live: basecamp.com's actual tagline is a plain <h1>, genuinely on the page,
# but trafilatura's main-content heuristics dropped it -- most likely because it sits in a
# hero/<header>-style container it treats like navigation chrome. No prompt fix can help this;
# the text never reached the model. clean_page() now always folds the <h1> back in if missing.

HERO_HTML = """
<html>
<head><title>Basecamp</title></head>
<body>
<header><h1>Basecamp is project management without all the nonsense.</h1></header>
<main><p>Some other real body paragraph trafilatura is expected to extract normally.</p></main>
</body>
</html>
"""


def test_clean_page_folds_back_an_h1_that_trafilatura_dropped(monkeypatch):
    # Force trafilatura to behave the way it actually did on the real basecamp.com run --
    # returning real body text that does NOT include the <h1> -- so this test doesn't depend
    # on trafilatura's own heuristics behaving one way or another on a small synthetic fixture.
    monkeypatch.setattr(
        clean_module.trafilatura, "extract",
        lambda html, **kw: "Some other real body paragraph trafilatura is expected to extract normally.",
    )
    page = clean_page("https://example.com/", HERO_HTML, max_clean_chars=12000)
    assert "project management without all the nonsense" in page.text


def test_clean_page_does_not_duplicate_an_h1_trafilatura_already_kept():
    # If trafilatura's real extraction already includes the <h1> text, it must not be
    # duplicated by the fold-back logic.
    page = clean_page("https://example.com/", RICH_HTML, max_clean_chars=12000)
    assert page.text.count("project management without all the nonsense") == 1


# --- Always keep a postal-address-shaped block (decided 2026-09-27) -------------------------
# Real bug found live on razorpay.com/about (a "REGD. OFFICE ADDRESS" footer box) and
# gong.io/about (a card-style office-locations list) -- both hold the real full street address
# nowhere else on the page, and neither survived trafilatura's extraction. clean_page() now
# always folds a postal-address-shaped block back in if trafilatura dropped it.

FOOTER_ADDRESS_HTML = """
<html>
<head><title>Acme Payments</title></head>
<body>
<main><p>Acme Payments helps businesses accept payments online.</p></main>
<footer>
  <div>REGD. OFFICE ADDRESS</div>
  <div>Acme Payments Pvt Ltd, 1st Floor, SJR Cyber, 22 Example Road, Bengaluru, 560030</div>
  <div>Copyright 2026</div>
</footer>
</body>
</html>
"""


def test_clean_page_folds_back_a_footer_address_that_trafilatura_dropped(monkeypatch):
    # Force trafilatura to behave the way it does in production against a real footer box --
    # returning only the main-body paragraph, with the footer (address included) stripped.
    monkeypatch.setattr(
        clean_module.trafilatura, "extract",
        lambda html, **kw: "Acme Payments helps businesses accept payments online.",
    )
    page = clean_page("https://example.com/about", FOOTER_ADDRESS_HTML, max_clean_chars=12000)
    assert "22 Example Road, Bengaluru, 560030" in page.text


def test_clean_page_does_not_duplicate_an_address_trafilatura_already_kept():
    page = clean_page("https://example.com/about", FOOTER_ADDRESS_HTML, max_clean_chars=12000)
    assert page.text.count("22 Example Road, Bengaluru, 560030") == 1


def test_clean_page_ignores_a_street_name_or_bare_number_mentioned_in_passing():
    # Conservativeness check: a street-suffix word alone, or a five-digit number alone, must
    # not be treated as an address -- both signals are required together.
    html = (
        "<html><body><main>"
        "<p>Our office overlooks Example Road, a busy street in the city centre.</p>"
        "<p>Over 56000 customers trust our platform every day.</p>"
        "</main></body></html>"
    )
    page = clean_page("https://example.com/", html, max_clean_chars=12000)
    assert "Example Road" in page.text  # kept because it's real body text, just not re-added
    assert page.text.count("Example Road") == 1  # not duplicated by the address fold-back


def test_clean_page_trusts_an_explicit_address_tag_on_its_own():
    html = (
        "<html><body><main><p>Some body copy.</p></main>"
        "<address>Acme HQ, One Infinite Loop</address>"
        "</body></html>"
    )
    page = clean_page("https://example.com/", html, max_clean_chars=12000)
    assert "One Infinite Loop" in page.text


# --- Page-priority character caps (decided 2026-09-22, see module docstring) ----------------

CONFIG = {
    "crawl": {
        "max_clean_chars": 12000,
        "priority_max_clean_chars": 16000,
        "priority_url_keywords": ["customer", "testimonial", "pricing"],
    }
}


def test_is_priority_url_matches_a_keyword_in_the_path():
    assert is_priority_url("https://example.com/customers", ["customer"])
    assert is_priority_url("https://example.com/support/testimonials", ["testimonial"])


def test_is_priority_url_does_not_match_unrelated_paths():
    assert not is_priority_url("https://example.com/guides/how-we-communicate", ["customer"])


def test_resolve_char_cap_gives_priority_pages_the_higher_cap():
    assert resolve_char_cap("https://example.com/customers", CONFIG) == 16000


def test_b47_widened_keywords_match_the_real_page_types_they_were_added_for():
    # B-47 (2026-09-27): config.yaml's priority_url_keywords gained these five specifically to
    # catch page types the held-out crawl was missing entirely -- confirms each one actually
    # matches a realistic URL of the page type it's meant to catch, not just a substring in
    # isolation.
    keywords = ["industr", "integrat", "trust", "secur", "complian"]
    assert is_priority_url("https://example.com/industries", keywords)
    assert is_priority_url("https://example.com/integrations", keywords)
    assert is_priority_url("https://example.com/trust", keywords)
    assert is_priority_url("https://example.com/security", keywords)
    assert is_priority_url("https://example.com/compliance", keywords)


def test_resolve_char_cap_gives_ordinary_pages_the_default_cap():
    assert resolve_char_cap("https://example.com/guides/some-post", CONFIG) == 12000


def test_resolve_char_cap_falls_back_to_default_when_priority_settings_absent():
    minimal_config = {"crawl": {"max_clean_chars": 12000}}
    assert resolve_char_cap("https://example.com/customers", minimal_config) == 12000


# --- B-61: a pricing page's call-to-action labels are folded back into the cleaned text ---

_PRICING_HTML = (
    "<html><head><title>Pricing</title></head><body><main><h1>Plans</h1>"
    "<p>" + "Our plans are simple and fair. " * 20 + "</p>"
    "<a href='/signup'>Get started for free</a> <button>Contact sales</button>"
    "</main></body></html>"
)


def test_b61_pricing_page_text_ends_with_the_cue_labels():
    from wi.crawl.clean import clean_page
    page = clean_page("https://x.example/pricing", _PRICING_HTML, 12000)
    assert "Buttons and links on this page:" in page.text
    tail = page.text.split("Buttons and links on this page:")[1]
    assert "Get started for free" in tail and "Contact sales" in tail


def test_b61_non_pricing_page_is_left_alone():
    from wi.crawl.clean import clean_page
    page = clean_page("https://x.example/about", _PRICING_HTML, 12000)
    assert "Buttons and links on this page:" not in page.text


def test_b61_cue_lines_survive_truncation_of_a_long_pricing_page():
    from wi.crawl.clean import clean_page
    page = clean_page("https://x.example/pricing", _PRICING_HTML, 100)
    assert page.truncated
    assert "Contact sales" in page.text.split("Buttons and links on this page:")[1]


def test_b61_pricing_page_without_cta_labels_gets_no_block():
    from wi.crawl.clean import clean_page
    html = "<html><body><main><h1>Plans</h1><p>" + "Simple pricing. " * 20 + "</p></main></body></html>"
    page = clean_page("https://x.example/pricing", html, 12000)
    assert "Buttons and links" not in page.text


# --- B-92: certification badge grids are folded back in -------------------------------------------

def _security_page(main_extra="", outside=""):
    """Synthetic page shaped like a compliance page: prose that trafilatura keeps, plus whatever
    the test adds inside <main> and outside it."""
    prose = ("<p>We protect customer data with encryption in transit and at rest, regular "
             "penetration tests and a dedicated security team. Our trust centre lists every "
             "audit report and policy, and customers can request documents at any time.</p>") * 6
    return (f"<html><head><title>Security</title></head><body>"
            f"<nav><a href='/'>Home</a></nav><main><h1>Security at Acme</h1>{prose}{main_extra}</main>"
            f"{outside}</body></html>")


BADGE_GRID = (
    '<section><h2>Compliance is a proof point.</h2><div class="BadgeGrid__strip">'
    + "".join(f'<div class="BadgeGrid__badge"><img alt="{n} certified." src="/b/{i}.png"/>'
              f'<span class="BadgeGrid__label">{n}</span></div>'
              for i, n in enumerate(["SOC 2 Type II", "PCI DSS", "HIPAA", "GDPR", "CCPA / CPRA",
                                     "CSA STAR", "TX-RAMP", "ISO 27001", "ISO 42001"]))
    + "</div></section>"
)


def test_b92_badge_grid_labels_are_folded_back_in():
    from wi.crawl.clean import CERT_BLOCK_HEADER
    text = clean_page("https://acme.test/security", _security_page(BADGE_GRID), 16000).text
    assert CERT_BLOCK_HEADER in text
    block = text.split(CERT_BLOCK_HEADER, 1)[1]
    for label in ["SOC 2 Type II", "PCI DSS", "HIPAA", "GDPR", "CCPA / CPRA", "CSA STAR",
                  "TX-RAMP", "ISO 27001", "ISO 42001"]:
        assert f"\n{label}" in block                    # one quotable line per label
    assert "certified." not in block                     # alt text is not used


def test_b92_footer_links_naming_certifications_are_not_folded_in():
    footer = ("<footer><ul><li><a href='/gdpr'>GDPR</a></li><li><a href='/soc2'>SOC 2</a></li>"
              "<li><a href='/hipaa'>HIPAA</a></li></ul></footer>")
    text = clean_page("https://acme.test/security", _security_page(outside=footer), 16000).text
    assert "Certification and compliance badges:" not in text


def test_b92_cookie_banner_mentioning_gdpr_is_not_folded_in():
    banner = ('<div id="cookie-consent" class="consent-banner"><span>GDPR</span><span>CCPA</span>'
              '<span>HIPAA</span><button>Accept all</button></div>')
    for placement in ("main", "outside"):
        page = _security_page(main_extra=banner) if placement == "main" else _security_page(outside=banner)
        text = clean_page("https://acme.test/security", page, 16000).text
        assert "Certification and compliance badges:" not in text, placement


def test_b92_a_single_soc2_mention_is_not_folded_in():
    single = '<div class="badge"><span>SOC 2</span></div>'
    text = clean_page("https://acme.test/security", _security_page(single), 16000).text
    assert "Certification and compliance badges:" not in text


def test_b92_prose_naming_three_certifications_is_not_a_badge_grid():
    prose = ("<div><p>Our programme is audited every year against SOC 2, aligned with ISO 27001 "
             "and designed to help customers meet HIPAA obligations where they apply to them.</p></div>")
    text = clean_page("https://acme.test/security", _security_page(prose), 16000).text
    assert "Certification and compliance badges:" not in text
