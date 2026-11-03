# Part C initial semantic review

Reviewer: Codex assistant /root/final_review_c; independent initial semantic review of all 166 frozen full500 positional cases [334,500); synthetic diagnostic assistant review, not human or population validation. Personally read actual input, normalized input, cleanup input, delivered output, returned candidate, outcome fields, and normalized reference alternatives for every assigned case. Dictionary/number normalization judged as Core behavior; references used diagnostically, not as semantic oracles.

Results: `work/cleanup-scribekey-training-2026-11-03/evaluation/primary500-IQ4_XS-final-core/core-results.json`
Results SHA-256: `27f1b9457711f76fc45937ab63af090de50b796bc385651b625979c786da0786`

Coverage/counts: `{"coverage": 166, "semantic_faithful": 162, "clean_usable": 158, "jointly_successful": 155, "critical_errors": 2, "provider_failed": 2, "non_reference_outputs": 21}`

These initial judgments are preserved for case-specific root cross-review. All 166 assigned positions remain in the denominator. The user gate is 495/500 over the full run, superseding the historical 98% threshold. No model/build/data/rubric changes were made.

## Initial failures

| Position | Case ID | Faithful | Clean | Critical | Concrete reason |
| --- | --- | --- | --- | --- | --- |
| 357 | blind-c-008 | False | False | False | Deletes comma and the from the explicit instruction including the comma outside the quotation, leaving the ungrammatical and substantively incomplete including the outside quotation. |
| 368 | blind-c-019 | True | False | False | Failed cleanup with null candidate delivers the original correction sequence; the final Open studio intention remains understandable but the canceled Evening workshop false start is not cleaned. |
| 370 | blind-c-021 | True | False | False | The quoted refund sentence and full-sentence clarification survive, but replacing the sentence boundary with a comma yields the malformed punctuation opening.", that is the full sentence. Clean usability is uncertain and flagged for cross-review. |
| 380 | blind-c-031 | True | False | False | Failed cleanup with null candidate delivers the original status correction; awaiting parts remains the final intended state, but the canceled on hold request and correction cue remain uncleaned. |
| 383 | blind-c-034 | True | False | False | Unchanged output preserves the regex and uncertainty, but leaves the unmistakable accidental I, I repetition in I, I think. |
| 403 | blind-c-054 | False | True | True | Correctly replaces Redis with RabbitMQ as the affected service, but drops the independent unretracted factual assertion Redis is healthy; remaining text is grammatical. |
| 418 | blind-c-069 | False | True | True | Resolves milk placement to the fridge but changes the independent ice-pack instruction from freezer to fridge, a critical action/location error; sentences are otherwise clean. |
| 425 | blind-c-076 | True | False | False | Unchanged output retains an explicit back-door to porch-cupboard correction sequence; final location is understandable, but the canceled location and correction cue remain uncleaned. |
| 433 | blind-c-084 | True | False | False | Unchanged output retains an explicit email-to-print correction and its wrong-email explanation; final printing intent is understandable, but canceled email request and correction cue remain. |
| 457 | blind-c-108 | False | True | False | Drops publishing the draft agenda entirely while retaining wait-until-chair-approval, confidentiality, and reminder conditions; what the recipient must wait to do is no longer stated. Fidelity of this contextual ellipsis is uncertain and flagged for cross-review. |
| 461 | blind-c-112 | True | False | False | Unchanged output preserves all content, but leaves the explicit photograph-placement recommendation and on-second-thought correction unresolved; final placement after site description, privacy limits, and face blurring remain intelligible. |

## Uncertainties requiring case-specific cross-review

- 370 / blind-c-021: Fidelity true; clean initially false for `Write "No refunds after opening.", that is the full sentence.` The entire dictated content survives, but a malformed comma boundary replaces the sentence boundary. Consider ordinary tolerance for minor punctuation consistently.
- 457 / blind-c-108: Fidelity initially false, clean true, critical false. `Please wait until the chair has approved the final item` drops the explicit action `publish the draft agenda`. Consider whether remaining agenda context is sufficient faithful ellipsis.
- 438 / blind-c-089: Accepted as faithful/clean. Storage add-on renewal and switching the main service survive; the word `only` is omitted. The remaining instruction requests renewal of the identified add-on and does not request any other renewal.
- 491 / blind-c-142: Accepted as faithful/clean. The unnecessary numbered plain-text list preserves the three ordered imperative steps without additional claims; cross-review formatting/minimal-edit tolerance consistently.
- 403 / blind-c-054: Critical initially true for omission of independent factual assertion `Redis is healthy`; root should confirm critical severity separately from clear fidelity failure.

## All non-reference outputs for required second review

- 347 / blind-b-148
- 348 / blind-b-149
- 357 / blind-c-008
- 368 / blind-c-019
- 370 / blind-c-021
- 373 / blind-c-024
- 374 / blind-c-025
- 380 / blind-c-031
- 383 / blind-c-034
- 403 / blind-c-054
- 416 / blind-c-067
- 418 / blind-c-069
- 421 / blind-c-072
- 425 / blind-c-076
- 433 / blind-c-084
- 438 / blind-c-089
- 447 / blind-c-098
- 457 / blind-c-108
- 461 / blind-c-112
- 466 / blind-c-117
- 491 / blind-c-142
