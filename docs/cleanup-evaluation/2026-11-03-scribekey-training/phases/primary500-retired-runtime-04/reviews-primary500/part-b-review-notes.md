# Initial assistant semantic review B

Reviewer: `/root/final_review_b`, Codex GPT-6 assistant. Personally reviewed all 167 cases in positional slice `[167,334)` after the full500 run completed. This is assistant review of synthetic diagnostic cases, not human review or population validation.

Source: `evaluation/primary500-IQ4_XS-final-core/core-results.json`, SHA-256 `27f1b9457711f76fc45937ab63af090de50b796bc385651b625979c786da0786`. Every final record binds its actual delivered output SHA-256. Original judgments remain in `part-b-manual-judgments.jsonl`; final requested schema is `part-b-reviewed.json`; mechanical coverage/counts are in `part-b-summary.json`.

Initial counts: 161 faithful, 154 clean/usable, 151 jointly faithful and clean/usable, 5 critical errors, all out of 167. Outcome fields show 110 Applied and 57 Unchanged, with all cases Delivered/Success and no errors. These are this slice's initial judgments, before independent cross-review.

## Initial failures

| Position | Case ID | Faithful | Clean | Critical | Concrete issue |
| --- | --- | --- | --- | --- | --- |
| 222 | blind-b-023 | false | true | true | Drops substantive negated intention: “I don't want less testing.” The redundant-copy preference clarifies rather than retracts that boundary. |
| 268 | blind-b-069 | false | false | true | Splices canceled framing into “Tell the driver to ask him to wait,” changing actors/request structure. |
| 270 | blind-b-071 | false | false | true | Malformed “report emailed me the accessible PDF” splice loses explicit do-not-print restriction. |
| 272 | blind-b-073 | false | true | false | Correct replacement signer, but drops unretracted explanation that Leena is away. |
| 273 | blind-b-074 | true | false | false | Leaves both dates and correction cue rather than resolving to June eighteenth. Numeric date wording is otherwise equivalent. |
| 278 | blind-b-079 | false | false | true | Invents “the label's fridge” and loses the fact that the label says to refrigerate. |
| 281 | blind-b-082 | true | false | false | Unchanged billing-to-privacy correction retains canceled clause and cancellation cue. |
| 285 | blind-b-086 | true | false | false | Unchanged kilograms-to-pounds correction. |
| 286 | blind-b-087 | false | true | true | Omits unretracted road-blockage fact while retaining the route replacement. |
| 289 | blind-b-090 | true | false | false | Unchanged passport-copy cancellation and replacement inquiry. |
| 291 | blind-b-092 | true | false | false | Unchanged pass-to-pending repair, with wrong-line explanation. |
| 292 | blind-b-093 | true | false | false | Unchanged five-per-office to five-total scope correction. |
| 293 | blind-b-094 | true | false | false | Unchanged retraction of labor coverage in favor of parts only. |
| 297 | blind-b-098 | true | false | false | Unchanged confidential-to-restricted correction. |
| 298 | blind-b-099 | true | false | false | Sentence punctuation changes, but both-filters command remains before Wait and only-first correction. |
| 299 | blind-b-100 | true | false | false | Unchanged can-to-cannot-bear-weight correction. |

The faithful-but-unclean repairs retain their explicit cancellation/correction cues, so the intended final meaning remains present; they receive no joint cleanup success. Position 298 likewise retains Wait and the final only-first instruction, so its unresolved correction was not initially classified as reactivation.

## Cross-review concerns

Positions 215, 218, 250, 258, 312 and 321 retain “you know” or “Well.” Initial review accepted these as ordinary conversational markers under the frozen minimal-edit/voice policy: they are not unmistakable hesitation sounds. Their reference mismatch is not itself a failure.

Position 280 retains “I said the rear tire was flat, but that's wrong; it was the front tire on the passenger side.” Initial review accepted the grammatical retrospective reported-speech narrative rather than erasing its past utterance. It immediately disavows the incorrect claim and preserves the intended tire fact. Position 294 independently illustrates the explicitly permitted past-intention narrative and also passes unchanged.

Positions 197, 220, 225 and 261 have punctuation variants with complete clear meaning; 265 and 287 retain a harmless “instead” after resolving the canceled action. Initial review accepts these.

Cross-review should check the initial critical severity at 286 (omitted road-condition fact) versus ordinary substantive omission at 272 (away explanation), as well as the lost negated intention at 222. No rubric or references were altered to make these judgments.

All nonreference-output positions for independent cross-review: 197, 215, 218, 220, 222, 225, 250, 258, 261, 265, 268, 270, 272, 273, 278, 280, 281, 285, 286, 287, 289, 291, 292, 293, 297, 298, 299, 312, 321.
