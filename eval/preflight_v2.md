# Pre-flight for held-out set v2 (model-free)

Run on 2026-10-09, before any labelling, with the project's own code only: `validate_company_url`,
then `crawl_site` limited to the homepage (one page, depth 0, start-URL retries disabled for this
check, no JS rendering), which also fetches `robots.txt`. `crawl_status` and `crawl_error_code` use
the crawler's own rules (B-83, B-84, B-86); `site_language` and `non_english` use the B-85 detector
on the homepage text. No extraction or model call was made, no page text was printed or saved, and
nothing was written to `data/runs`, `data/clean` or `data/pages`.

| Site | crawl_status | crawl_error_code | Final host | site_language | non_english |
| --- | --- | --- | --- | --- | --- |
| miro.com | ok | - | miro.com | en | False |
| leadsquared.com | ok | - | www.leadsquared.com | en | False |
| cashfree.com | ok | - | www.cashfree.com | en | False |
| athenahealth.com | blocked | SITE_BLOCKED | athenahealth.com | - | - |
| cohere.com | ok | - | cohere.com | en | False |
| fractal.ai | unreachable | SITE_UNREACHABLE | fractal.ai | - | - |
| framer.com | ok | - | www.framer.com | en | False |
| chargebee.com | ok | - | www.chargebee.com | en | False |
| mercury.com | ok | - | mercury.com | en | False |
| elevenlabs.io | ok | - | elevenlabs.io | en | False |

A site that is not `ok` or not English is reported here, not replaced; any replacement is decided
by Uttam and logged in `eval/benchmark_sites_v2.md` under the eligibility rule.
