# Optional specialist literal protocol v4

V4 protects complete paired ASCII single quotes (`'…'`) and curly single quotes
(`‘…’`), in addition to dictionary blocks and paired ASCII/curly double quotes.
It does not protect ordinary unquoted filenames, codes or identifiers. It changes
the input transport and exact restoration contract; it adds no semantic editing
rule. A new model/profile must be evaluated under that contract. Historical v3
results do not establish v4 quality.

Existing calls, manifests, prompt exports and training loaders continue to use
v3. The training `pipeline.py` is unchanged. Opt in explicitly:

- C#: `SpecialistLiteralMask.Create(text, protocol: SpecialistLiteralProtocol.CompactV4)`.
- Managed options/manifest: enable `maskSpecialistLiterals` and set
  `specialistLiteralProtocol` to the string `CompactV4`. V4 requires a specialist
  prompt style. Unknown versions and incorrectly typed values fail validation.
- Python: `SpecialistLiteralMask.create(text, protocol="specialist-compact-v4")`
  from `Freehand.Cleanup.Evaluation/specialist_literal_protection.py`.
- Probe prompt export: `--mask-specialist-literals true
  --specialist-literal-protocol specialist-compact-v4`.
- New evaluator freeze: `--specialist-literal-protocol specialist-compact-v4`.
  The freeze declares the version, its profile contains `CompactV4`, prompt export
  uses v4, and actual Core metadata must report `specialist-compact-v4`. A missing,
  mismatched or untyped declaration cannot silently replay v3. Default v3 freezes
  retain their existing profile fields and do not require the new metadata field.

## Quote boundaries

The bounded scanner uses at most 64 nested delimiters and emits only complete
outer spans, so nested/mixed quotes never overlap. Dictionary blocks are masked
first. Their contents cannot create quote boundaries; restoration expands them
exactly afterward. Quote characters preceded by an odd number of backslashes are
data. Balanced quotes may contain whitespace, tabs, newlines, Unicode, quoted
hesitations and instruction-like text; none of those contents is editable.

Apostrophes between word scalars are data (`don't`, `we're`, `it's`, `we’re`).
Word scalars are exactly the frozen Unicode14 letter, number, mark and connector
categories, not the host runtime's changing Unicode database. A trailing
possessive such as `James'` does not open a quote. Both `James' notebook says
'come later'.` and `The note says 'come later' in James' notebook.` protect only
the paired wording. Word-final `-in'`/`-in’` shortenings remain data outside quotes.

The common leading elisions `'cause`, `'em`, `'tis` and their right-curly
apostrophe forms remain data when not immediately paired. The explicitly paired
`'cause'` is a literal. The elision names use ASCII case matching. This is a
defined lexical boundary, not an attempt to recognize all English elisions.
The same elisions remain ordinary inside a complete outer quote, which is
protected in full; an immediately paired `'em'` still forms a nested literal.

V4 rejects unmatched opening quotes, unmatched/crossing curly delimiters,
excessive nesting and invalid Unicode scalar input before worker startup.
Same-delimiter nested straight quotes open at a word-opening boundary and close
at an end boundary. A terminal bare apostrophe that could close an earlier
same-family quote, rather than a following possessive noun, is ambiguous; for
example `'James' notebook'` rejects. A leading elision followed by an otherwise
unmatched terminal quote also rejects. Ambiguous bare possessives at clause end
may therefore fall back. This deliberately bounded grammar makes no claim to
parse every use of English quotation marks. V3 retains its original permissive
unmatched-double-quote behavior.

## Exact restoration and target compatibility

Each complete outer quote or dictionary span gets a deterministic compact token.
Every original token must survive exactly once and in source order. Missing,
duplicate, reordered or newly invented token families reject the result. Exterior
specialist `trim-v1` still runs before restoration. Hidden payload bytes, including
their leading/trailing whitespace, quote glyphs and punctuation, are restored
without normalization. The existing v3 terminal-period rule remains part of v4.
Raw model responses and restored output remain distinct evaluation fields.

Python exposes `masked_text`, `tokens`, intermediate `payloads`, and
`restore(complete_text)`. Intermediate payloads may contain dictionary tokens;
do not restore them individually. To obtain raw protected intervals for a copy
editor, put fresh collision-checked bookends around every original token in the
complete masked text, restore once, recover the intervals, and assert that
removing every bookend reproduces the original UTF8 bytes exactly. Keep Python
codepoint offsets distinct from managed UTF16 offsets.

Training targets must retain all source-protected payloads once and in order,
including obsolete quoted wording explicitly framed as inactive. A target that
deletes/reorders one is unsupported by this transport. Preserve that failure;
do not relabel, infer a target, or drop the example to claim compatibility.

## Reproducing the word table

Both generated modules contain the same inclusive Unicode14 word intervals and
canonical interval SHA256
`0f266cdd37e73c54ff7ca4f18194fccce6d4c550d846cb9e1921a482599b443a`.
The Python table loads only on v4; managed lookup also occurs only on v4. Scalars
assigned after Unicode14 retain their frozen nonword classification. No runtime
data files, new normalization or external dependencies are used.

`generate_specialist_word_ranges.py --unicode-data UnicodeData.txt` checks both
generated files without changing them. `--write` creates missing outputs and
refuses to replace existing files. The input must have SHA256
`36018e68657fdcb3485f636630ffe8c8532e01c977703d2803f5b89d6c5feafb`:
the official Unicode14 `UnicodeData.txt`, also retained by the Unicode project's
ICU `release-70-1/icu4c/source/data/unidata/UnicodeData.txt` mirror. This input pin
makes generation independent of the generator host's Unicode version.
The associated copyright/permission notice is in
[UNICODE-DATA-LICENSE.txt](../../docs/UNICODE-DATA-LICENSE.txt).

The new C#/Python table modules and generator belong to evaluator source
snapshots. Any separate trainer/copy-editor source-closure inventory must include
them explicitly. The shared scalar/UTF8 vectors and source-table equivalence
tests verify the transport, not cleanup quality or a new acceptance result.
