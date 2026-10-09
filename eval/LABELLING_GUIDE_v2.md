# Labelling guide: held-out set v2

For the 8 sites in `eval/benchmark_sites_v2.md`. Built from the field definitions in
`docs/PRD.MD` (Section 4, Section 5 rules, Section 12 ground truth) and the conventions already in
`eval/labels/_template_v2.json` and the dev labels. It adds no new field or status; where the
dev labels are inconsistent, that is listed under "Open points" rather than decided here.

## Before you start

1. **Write the three Decisions below first, then freeze them.** Do not change them once labelling
   has started.
2. **Label blind.** Do not run `run_site.py` (or any pipeline step) on these sites, and do not open
   anything under `data/runs/`, `data/clean/` or `data/pages/` for them, until the labels are
   checksummed and the code is tagged.
3. Label each site in one sitting where possible, and record the date in
   `labeling_metadata.date_labeled`, the company's own name in `labeling_metadata.company_name`,
   and anything unusual in `labeling_metadata.notes`. Then change its row in
   `eval/benchmark_sites_v2.md` from UNLABELED to LABELED.

## Where to look

Label from the **full live page text**, not screenshots (the dev labels were partly made from
screenshots, which missed text on pages the screenshots did not show). Read the actual pages in a
browser, including text further down the page and in the footer. For every site, check at least:

- homepage, including the footer
- about / company / contact pages (headquarters, description)
- product and platform pages, and the product menu
- pricing page (plans, amounts, trial, contact-sales or demo cues)
- customers / case studies / testimonials
- partners / integrations / marketplace pages
- security / trust / compliance pages (certifications), and legal pages where they state them
- comparison or "vs" pages (named alternatives)

## How to record a field

Follow the template's own rules (`labeling_instructions` in every label file); in short:

- **Source policy:** only what the company states on its own public website. No outside knowledge
  (PRD Section 5, rule 2: the underlying page is the evidence).
- **Statuses:** `extracted` (stated, with a verbatim or near-verbatim quote), `inferred` (only on
  the three whitelisted fields `pricing.sales_motion`, `pricing.revenue_model`,
  `products.delivery_model`, with a quote the inference rests on), `not_found`, `conflicting`
  (only for a single-valued field where two pages state incompatible facts).
- **One source per label:** every `extracted` or `inferred` field gets a `source_url` for the page
  its quote is on. For list fields, as in the dev labels, `value`, `evidence` and `source_url` are
  lists of the same length and order, one source page per item.
- **Evidence:** copy the page's own words. For list fields, one quote per item unless a single
  contiguous quote contains every item (`multi_value_evidence_rule`). Never let a paraphrase stand
  in as evidence.
- **`not_found` only after checking the likely pages above** for that field. If you want to record
  which pages you checked, put it in that field's `notes`. A field left at the template's default
  `not_found` without checking is the most damaging error: it scores a correct pipeline answer as
  "unsupported".
- **Notes:** use a field's `notes` for anything a later reader needs: why something was excluded,
  ambiguity, or a decision from the section below that applied.
- Field-specific rules are in each file's `labeling_instructions.field_specific_rules` (segments,
  industries, products.names, sales_motion, revenue_model, delivery_model, free_trial,
  certifications, partnerships, named_customers). Apply them as written.

## Decisions (write these before labelling, then freeze)

Context only, not a recommendation: the template says certifications are "Compliance/standards
marks (SOC 2, ISO, ...) or named partner-tier badges issued by a third party"; the Notion dev label
excluded GDPR and CCPA as "policy alignment/mapping, not a third-party-issued certification". The
template says partnerships are "Named companies described as integration, channel, or technology
partners". The template says a product name counts if it is "a nav item linking to its own product
page, a product-page title/heading, or explicit 'Introducing X' branding".

**(a) Laws and frameworks shown as badges** (for example GDPR, CCPA/CPRA badges next to SOC 2 or
ISO badges): do they count as `traction.certifications`?

Decision:

**(b) `traction.partnerships`:** named partners only, or integrations (apps the product connects
to) too?

Decision:

**(c) List fields** (`products.names`, `traction.named_customers`, `customers.industries`,
`traction.certifications`, `traction.partnerships`, `comparisons.named_alternatives`,
`pricing.public_plans`): how many names count (all that the site states, or a cap), and do
navigation-menu items count as products?

Decision:

Decided by: ____________   Date: ____________

## Open points noticed in the dev labels (not decided here)

- `pricing.public_plans`: Calendly's label records "plan name and price" ("Standard — $10/seat/mo");
  the other four dev labels record plan names only. B-58's scoring convention is "plan name plus
  price".
- `products.delivery_model`: the dev labels use free-text descriptions ("Digital software delivered
  online with a downloadable app"), while the PRD lists categories (software, service, marketplace,
  physical) and the pipeline reports a category with channels ("software (desktop app, mobile
  app)"). See `docs/KNOWN_LIMITATIONS.md`.
- `pricing.sales_motion`: four dev labels use the short form "Self-serve and sales-led"; Calendly's
  spells out which plans are which.

If you settle any of these, write it next to the three Decisions above before labelling.
