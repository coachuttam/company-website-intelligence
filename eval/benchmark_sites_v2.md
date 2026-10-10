# Fresh held-out set v2

**Selected:** 2026-10-09, by Uttam. **User-supplied before any pipeline output was seen** for these
sites: none of them has been run through `run_site.py`, and no extraction, cleaning output or
rendered page exists for any of them. Ten sites were selected; two were excluded the same day for
crawl-status reasons (see the replacement log), leaving the **final set of 8**:

| # | Site | Label file | Label status |
| --- | --- | --- | --- |
| V1 | miro.com | `eval/labels/heldout_v2/miro.json` | LABELED |
| V2 | leadsquared.com | `eval/labels/heldout_v2/leadsquared.json` | LABELED |
| V3 | cashfree.com | `eval/labels/heldout_v2/cashfree.json` | LABELED |
| V4 | cohere.com | `eval/labels/heldout_v2/cohere.json` | UNLABELED |
| V5 | framer.com | `eval/labels/heldout_v2/framer.json` | LABELED |
| V6 | chargebee.com | `eval/labels/heldout_v2/chargebee.json` | UNLABELED |
| V7 | mercury.com | `eval/labels/heldout_v2/mercury.json` | LABELED |
| V8 | elevenlabs.io | `eval/labels/heldout_v2/elevenlabs.json` | LABELED |

**Sample size:** n = 8, so each per-field score moves in steps of 12.5 points (one site), and the
headline moves by about 0.8 points per field-site. Results from this set must be read as
indicative, not precise.

The label files were created from `eval/labels/templates/_template_v2.json` with nothing filled in. In that
template every field starts as `not_found`, so an unlabelled file is indistinguishable from a site
that genuinely says nothing (the same problem `eval/labels/LABELING_STATUS.md` exists for). Update
the "Label status" column by hand as each file is labelled; `eval/checksum_labels.py --write`
also refuses to run while any file still has the template's `YYYY-MM-DD` date or an empty company
name.

## Layout

Since 2026-10-09 the label files are in subfolders of `eval/labels/` (moved with `git mv`, contents
unchanged): `dev/` (the 5 dev labels, read by `eval/baseline.py`), `heldout_v1_archived/` (the
original 10 held-out labels, contaminated, read only by `eval/held_out.py`), `heldout_v2/` (these 8,
read by `eval/checksum_labels.py`), `templates/` (`_template.json`, `_template_v2.json`) and
`archive_old_dev/` (unchanged). `LABELING_STATUS.md` stays at the top. The contamination check
below was made before the move and names the old flat paths.

## Contamination check (2026-10-09)

Each of the 10 originally selected domains was searched for with and without `www.` and by slug (`miro_com`, `www_miro_com`,
`miro.json` ...) in `eval/peeked_sites.txt`, `eval/labels/`, `data/runs/` (including the run
cache), `data/clean/`, `data/pages/`, `eval/*report*.json` and `PROGRESS.md`: 228 files, **0 hits**.
`eval/peeked_sites.txt` lists 30 domains, and every domain with a run file, snapshot or rendered
page is on it; none of the 10 originally selected sites is.

Before the selection was fixed, an Appendix A verification pass on 2026-10-09 fetched each site's
homepage, `robots.txt` and `/pricing` with the project's own fetcher (no pipeline run, no model
call); only status codes, titles and counts were recorded, outside the repo. The model-free
pre-flight in `eval/preflight_v2.md` repeats the homepage check.

## The old held-out set is not used for the headline

The old 10-site held-out set (Razorpay, Buffer, Innovaccer, Sarvam AI, Temenos, Thoughtworks,
NoBroker, Gong, Plaid, Renaissance Technologies) is contaminated: after it was first run and scored,
fixes B-39 to B-54 were made using its failures, and B-51 re-labelled `customers.segments` in all
10 of its label files. It is **not** used for the AC-02 headline. Only this v2 set of 8 is.

## Eligibility rule

A site is replaced **only for a crawl-status reason**: the run reports `crawl_status` unreachable,
blocked or redirected off the domain, or the site is non-English (`non_english: true`). A site is
**never** replaced because of how the pipeline performs on it. Any replacement is logged below with
the date, the site removed, the reason (with the crawl status or pre-flight result that shows it),
and the site added; the replacement must also be checked against `eval/peeked_sites.txt` and
labelled by hand before the freeze.

### Replacement log

| Date | Removed | Reason | Added |
| --- | --- | --- | --- |
| 2026-10-09 | athenahealth.com | Crawl status only: `SITE_BLOCKED` (the homepage answers HTTP 403 to the crawler; `eval/preflight_v2.md`) | None: excluded, not replaced, by user decision |
| 2026-10-09 | fractal.ai | Crawl status only: `SITE_UNREACHABLE` (TLS failure in this Python environment; `eval/preflight_v2.md`) | None: excluded, not replaced, by user decision |

Both exclusions are real crawler failures on live sites, not test artifacts. They go into
`docs/KNOWN_LIMITATIONS.md` after the held-out run (that file is not edited now).
`eval/preflight_v2.md` keeps both failing rows as recorded.

## Freeze protocol (in this order)

1. **Label all 8 by hand**, following `eval/LABELLING_GUIDE_v2.md`, without running the pipeline
   on these sites or opening any of its output for them. Labels were made by Uttam with the help
   of Claude (evidence gathering and drafting) and screenshots of the live pages; no pipeline
   output was seen.
2. **Checksum:** `python eval/checksum_labels.py --write` writes `eval/labels_v2.sha256`.
3. **Tag the code** `pre-heldout-v2` (only after steps 1 and 2).
4. **Run once:** `python run_site.py <url> --no-cache` for each of the 8 sites on the tagged code,
   after `python eval/checksum_labels.py --verify` passes.
5. **Report all 8 results**, including bad ones and any site that comes back unreachable or
   blocked.
6. **No tuning on these sites afterwards.** Once run, they join `eval/peeked_sites.txt`.
