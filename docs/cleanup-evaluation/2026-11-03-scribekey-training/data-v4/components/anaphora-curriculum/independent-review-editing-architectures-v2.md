# Independent semantic target review of anaphora V2

Reviewed all 120 frozen source/target pairs personally as an assistant reviewer. Source SHA-256: `4b8d5f75340a4f4b819031aa16e431b405250e71a8bb80b97b7634de1a0077ea`. No blind case contents, model runs, or source/dataset modifications. This is not human review.

117 pairs pass without a suggested change. No clear critical semantic errors were found. All object/attribute/quantity carryover, outer request recipients, reported frames, question/tense/voice, negation, neighboring substantive actions, and unresolved-reference controls are acceptable. Case 063 V2 correctly retains both the before-reset recording condition and the until-approval prohibition.

Cases 050, 054 and 058 drop the explicit temporal connector **then**. The target lists preserve action order, so these are avoidable temporal weakenings rather than clear critical errors. The data is semantically usable as-is; for conservative training gold, recommend a separately versioned three-case target overlay retaining then. The frozen V2 dataset remains unchanged.

| Case | Suggested target, not applied |
|---|---|
| 050 | Check the boiler pressure, then leave the small hose attached and record the reading before lunch. |
| 054 | Take a photograph of the scratched cover, then leave the cover untouched and include a ruler in the photograph. |
| 058 | Save the scanned letter, then keep the paper original in the fireproof cabinet and note where it is filed. |

Casewise notes and input/target SHA-256 bindings are in `independent-review-editing-architectures-v2.json`. A second assistant reviewed only these three connector concerns and reached the same distinction; all 120 were reviewed by the primary reviewer.
