# Dev-set labeling status

Tracks manual labeling progress for the dev set. This file exists because the label JSON schema
has no valid "pending" status (`wi/schemas/claim.py` only allows `extracted`, `inferred`,
`not_found`, `conflicting`), so a not-yet-labeled file is indistinguishable from a genuinely
all-`not_found` site by content alone. Check here before trusting any dev-set score.

## Dev set (5 sites, replaced 2026-09-28)

| File | Company | Status | Notes |
| --- | --- | --- | --- |
| `calendly.json` | Calendly | **LABELED** (2026-10-04) | Hand-labeled by Uttam. |
| `loom.json` | Loom | **LABELED** (2026-10-04) | Hand-labeled by Uttam. |
| `typeform.json` | Typeform | **LABELED** (2026-10-04) | Hand-labeled by Uttam. |
| `notion.json` | Notion | **LABELED** (2026-10-04) | Hand-labeled by Uttam. |
| `simplestores.json` | SimpleStores | **LABELED** (2026-10-04) | Hand-labeled by Uttam. |

## What UNLABELED means here

Every field in these 5 files currently reads `{"status": "not_found"}` -- not because the site
was checked and found to say nothing, but because no one has looked yet. Do not run
`eval/baseline.py` (or `eval/score_one.py` against one of these names) and treat the result as a
real accuracy number until every row above is updated to **LABELED**. Scoring an unlabeled file
would silently compare the system's output against an all-abstention answer key, which would
misreport genuine extractions as `unsupported` (the most serious scoring bucket) rather than
correct.

**Update this table by hand** (change UNLABELED -> LABELED, add the date) as each file is
actually labeled. This file is not read by any evaluation script -- it is a human checklist only.

## Archived (previous dev set, replaced 2026-09-28)

Moved to `eval/labels/archive_old_dev/`, not deleted: `basecamp.json`, `darwinbox.json`,
`zerodha.json`, `bajajauto.json`, `thoughtbot.json`. These were fully labeled and, per earlier
review, at least one (`basecamp.json`) had a confirmed error (see the `customers.segments`/
evidence-paraphrase issue discussed before this swap). Kept for reference, not part of the
active dev set, and not read by `eval/baseline.py` anymore.
