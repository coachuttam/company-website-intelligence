"""The 15 frozen schema fields (Final PRD, groups A-F), in the same order as
eval/labels/_template.json so the automated extractor and the hand labels are
always talking about the exact same field set.

RESOLVED (2026-09-26): "pricing.revenue_model" was previously whitelisted for
inference in wi/schemas/claim.py's INFERENCE_WHITELIST but missing from this
list entirely, so it could never actually appear in a run. Checked against the
approved Final PRD, Section 4, Group D: "Delivery model, revenue model, sales
motion and actual pricing are separate fields" -- the PRD explicitly requires
revenue_model as its own field, distinct from products.delivery_model and
pricing.sales_motion. This file was the one that was incomplete, not the
whitelist entry; added below.
"""
from __future__ import annotations

FIELDS = [
    "company_identity.name",
    "company_identity.description",
    "company_identity.headquarters",
    "products.names",
    "products.delivery_model",
    "customers.segments",
    "customers.industries",
    "pricing.public_plans",
    "pricing.sales_motion",
    "pricing.free_trial",
    "pricing.revenue_model",
    "traction.named_customers",
    "traction.certifications",
    "traction.partnerships",
    "comparisons.named_alternatives",
]

# Fields whose natural answer is a list of distinct named things (decided 2026-09-22, alongside
# widening Claim.value to accept a list -- see wi/schemas/claim.py). These are asked to come
# back as a JSON array of strings, one item per named thing; every other field stays a single
# string. This mirrors how eval/labels/*.json were already hand-labelled.
#
# "pricing.public_plans" added 2026-09-24: this field was never in the original set, but every
# live run and the hand-labelled basecamp.com reference have consistently returned it as a list
# anyway (one entry per named plan) -- the model and the labeller both treated it as obviously
# list-shaped even though rule 5 in wi/extract/prompt.py never told them to. Formalising it here
# closes that gap and, combined with the new field-shape check in wi/schemas/claim.py, means a
# claim can no longer silently disagree with this set (see that file's docstring).
MULTI_VALUE_FIELDS = {
    "products.names",
    "customers.industries",
    "traction.named_customers",
    "traction.certifications",
    "traction.partnerships",
    "comparisons.named_alternatives",
    "pricing.public_plans",
}
