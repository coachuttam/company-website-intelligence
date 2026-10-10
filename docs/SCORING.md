# Scoring

The scorer is `wi/eval/scoring.py`; the rules for the strict metric are in its module docstring
and in PRD Section 12. This file records the optional category-normalised metric (B-99).

## Category-normalised metric (post-hoc, secondary)

The strict headline stays the recorded result. The held-out v2 result, for example, is 35% strict.
The normalised metric is an extra reading, printed only with `--normalised` on `eval/baseline.py` or
`eval/held_out.py`.

**Why it exists.** The dev and held-out v2 labels write two fields in different styles, so strict
matching treats them differently:

| Field | Dev labels | v2 labels | The system emits |
| --- | --- | --- | --- |
| `products.delivery_model` | "Digital software delivered online" | "Software: description" | "software (API)" |
| `pricing.revenue_model` | "Subscription" | "Subscription tiers plus transaction fees" | "subscription" |

The normalised metric compares only the category of the two values, so the dev and v2 numbers are
read the same way. The same rules are applied to both sets.

**Rules.** These were fixed on 2026-10-11, before any number was computed (`wi/eval/normalise.py`).

- **A. Scope.**
  - Only `products.delivery_model` and `pricing.revenue_model`, and only verdicts that are
    `incorrect`. These are taken after the semantic judge, when it ran.
  - A match turns `incorrect` into `correct_normalised` or `correct_partial_normalised`. Both count
    as right calls in the normalised headline only.
  - Nothing is ever downgraded. `miss`, `unsupported`, `correct_abstention` and every other verdict
    are untouched.
  - If either side has no recognisable category, the original verdict stays.
- **B. `delivery_model` categories:** software, service (also "services"), marketplace, physical.
  - A value's category is its leading word, lowercased, when that word is one of these.
  - Otherwise it is the earliest of them that appears as a whole word in the text.
  - Otherwise it has none.
  - Equal categories give `correct_normalised`.
- **C. `revenue_model` categories:** keywords are matched as whole words or phrases, casefolded.

  | Category | Keywords |
  | --- | --- |
  | subscription | subscription, subscriptions, per-seat, per seat, per-user, per user, seat-based, recurring |
  | usage | usage, usage-based, pay-as-you-go, pay as you go, pay-per-use, pay per use, metered, consumption, volume-based |
  | transaction | transaction, transaction-based, transaction fees, take rate, commission, percentage fee, interchange |
  | one_time | one-time, one time, perpetual, lifetime, license fee |

  A value's category set is every category with a keyword hit.
  - Equal non-empty sets give `correct_normalised`.
  - Overlapping but unequal sets give `correct_partial_normalised`, which counts as correct, in line
    with how list fields are scored.
  - Disjoint or empty sets: no change.
- **D. The default output is unchanged.** Without `--normalised`, the strict metric, the CLI output
  and the report JSON are exactly as before. With it, a separate "category-normalised (post-hoc,
  secondary)" block is printed and a separate `normalised` key is added to the report. The two new
  verdict names are not part of the strict `Verdict` set.

**Limits.**
- The metric credits the right category even when the description is thin. For example,
  "subscription" against "Subscription tiers plus transaction fees" counts as partial.
- It is a reading aid for comparing the two label sets, not a replacement for the strict score.
- Any future fix should still be judged on the strict metric on a fresh set labelled under one
  convention.
