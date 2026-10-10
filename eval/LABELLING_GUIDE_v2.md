# Labelling guide: held-out set v2

For the 8 sites in `eval/benchmark_sites_v2.md`. Built from the field definitions in
`docs/PRD.MD` (Section 4, Section 5 rules, Section 12 ground truth) and the conventions already in
`eval/labels/templates/_template_v2.json` and the dev labels. It adds no new field or status; where the
dev labels are inconsistent, that is listed under "Open points" rather than decided here.

## Before you start

1. **Write the four Decisions below first, then freeze them.** Do not change them once labelling
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

Decision: NO. A law or regulation (GDPR, CCPA/CPRA, HIPAA as a law) is not a certification, even
when a badge says "compliant". `traction.certifications` counts third-party attestations, standards
and assurance programmes the site presents as credentials: SOC 1/2/3, ISO standards, PCI DSS,
HITRUST, FedRAMP, CSA STAR, TISAX, IRAP, vendor assurance programmes (e.g. Microsoft SSPA). Where a
badge carries no status wording, the item still counts and the notes say so. Anything excluded under
this rule is named in that field's notes.

**(b) `traction.partnerships`:** named partners only, or integrations (apps the product connects
to) too?

Decision: NAMED PARTNERS ONLY. Count a company when the site presents it as a partner (partner
programme or directory, technology / channel / strategic / solution partner). A plain integrations
or app-marketplace list does not count. Where a programme has tiers and a long directory, label the
top tier (up to 15 names) and state in notes how many partners exist and which tiers were not
labelled.

**(c) List fields** (`products.names`, `traction.named_customers`, `customers.industries`,
`traction.certifications`, `traction.partnerships`, `comparisons.named_alternatives`,
`pricing.public_plans`): how many names count (all that the site states, or a cap), and do
navigation-menu items count as products?

Decision:

- Label every name the site clearly states, except `traction.named_customers` and
  `traction.partnerships`, which are capped at 15, chosen by prominence: names in a sentence about
  customers, featured case-study headlines or attributions, the top partner tier.
- A customer or partner counts only if its name appears as visible text (sentence, headline,
  attribution line) or in logo alt text that was checked. Logo-only entries with no readable name
  text are not labelled; notes list them.
- Matching in scoring is exact after casefolding, so use the site's own spelling, taken from the
  page that is dedicated to the topic (security page for certifications, product menu for
  products). Put alternate spellings in notes. Never list the same item twice under two spellings.
- `products.names` follows the template rule: a proper name with its own product page. General
  pages (Security, Integrations, Pricing, Docs, Download Apps) and generic words (Whiteboard,
  Slides, Tables) do not count. Navigation items count only if they meet the rule.
- `customers.industries`, `comparisons.named_alternatives`, `pricing.public_plans`: all stated. A
  tool named only as an import source, or only inside a customer quote, is not an alternative.

**(d) `company_identity.headquarters`:**

Decision: label a place only if a page says it is the headquarters, head office or where the
company is based. A postal or notices address on a legal page, or a list of offices, is not a
headquarters statement: label `not_found` and record the address and offices in notes.

**Open points, settled for all 8 sites:**

- `pricing.public_plans`: "Plan name — price/unit" in the style of the Calendly dev label; billing
  period goes in notes.
- `products.delivery_model`: one sentence in the form "Category: description in the site's own
  terms" (categories: software, service, marketplace, physical), status `inferred`, with the quotes
  it rests on.
- `pricing.sales_motion`: the short form "Self-serve", "Sales-led", or "Self-serve and sales-led";
  which plans are which goes in notes.

Decided by: Uttam, with Claude (labelling help). Date: 2026-10-10. Written after the Miro draft and
before the other 7 labels and before any pipeline output for these sites; Miro's label was drafted
under the same rules.

## Open points noticed in the dev labels (settled above)

- `pricing.public_plans`: Calendly's label records "plan name and price" ("Standard — $10/seat/mo");
  the other four dev labels record plan names only. B-58's scoring convention is "plan name plus
  price".
- `products.delivery_model`: the dev labels use free-text descriptions ("Digital software delivered
  online with a downloadable app"), while the PRD lists categories (software, service, marketplace,
  physical) and the pipeline reports a category with channels ("software (desktop app, mobile
  app)"). See `docs/KNOWN_LIMITATIONS.md`.
- `pricing.sales_motion`: four dev labels use the short form "Self-serve and sales-led"; Calendly's
  spells out which plans are which.

If you settle any of these, write it next to the four Decisions above before labelling.
