# Local cleanup model research inventory

Start with [the synthesis and test shortlist](../../TRANSCRIPT-CLEANUP-SMALL-MODELS.md).
This directory preserves authored reports, structured catalogs, query/probe logs
and primary-source indexes from the October 30, 2026 research task.

## Coverage

| Workstream | Documented coverage | What the count means |
|---|---|---|
| Specialists | 30 HF keyword/tag queries, 16 web queries; 84 selected repository records | The broad HF queries returned 1,948 distinct IDs including irrelevant hits. Exports, aliases and multiple quants are not independent models. |
| S1-mini | 11 artifact variants, six alternative formats; exact-base filter returned 24 repos | One trained family plus a separately described fine-tune and conversion leads. Broad name search also returned unrelated models. |
| Compact controls | 72 endpoints requested, 69 resolved; 36 variants across 14 family groups | General controls, not 36 cleanup specialists. Three unresolved guessed endpoints are retained as failures. |
| Editing alternatives | 50 identifiers attempted, 46 resolved; 11 architecture/component records | Ready checkpoints, partial components and research/training architectures remain separate. |
| Products | 20 product/integration paths; 18 pinned Git repositories and 90 source files | Offline recognition and offline enhancement are checked separately. Plans and beta SDKs do not become shipping evidence. |
| Runtime | 44 indexed source/config snapshots and eight staged profiles | Pinned implementation evidence and proposed experiments, not new performance measurements. |
| Data resources | Ten dataset endpoints; public metadata/cards only | Includes access failures and mixed/gated terms. No rows, recordings or training downloaded/performed. |

This is a broad, reproducible, bounded search. It cannot establish that no other
model exists. The workstream counts overlap and must not be summed into a claim
about unique trained models. The complete logical index is
[catalog-index.json](catalog-index.json).

## What is verified

- Exact repository commits, metadata, trained contracts, model/config artifacts
  and published license text were checked where recorded.
- Catalog sizes and weight hashes are **publisher metadata**, not independently
  verified complete-weight downloads in this task.
- Twelve specialist and nine compact-control GGUF URLs passed tiny HTTP range
  probes with correct magic and advertised total sizes. These checks establish
  reachability/format prefix, not compatible execution or complete-file integrity.
- Performance and quality figures quoted by publishers retain their hardware,
  corpus, metric, protocol and scope qualifications.
- No new model inference, conversion, training, runtime builds or product changes
  were performed. No model has demonstrated the complete Freehand SLA here.

Source indexes retain URLs, immutable references and hashes of acquired text.
The original primary-source text cache remains in this workspace under
`work/cleanup-research-2026-10-30/`. Full unlicensed third-party documentation and
model-card prose are not republished here. A source index's cache path identifies
that acquisition, not a promise that its raw page is bundled in this directory.
Re-fetch the recorded immutable URL and compare its recorded hash when auditing.

## Use the records

[first-poc-shortlist.json](first-poc-shortlist.json) is a research plan, **not an
application acquisition manifest**. It names exact first-screen files, roles,
license caveats and source contracts. Do not feed it directly to setup tooling.
Confirm full download integrity, applicable notices, renderer/backend support
and trained prompt behavior before inference.

Use each model's own contract. A single universal prompt would invalidate this
comparison. Run quality and resource measurements separately, preserve raw
provider results and fallback coverage, and reserve a fresh final holdout after
configuration selection. Existing held-out Freehand outputs are now regression
data.

The historical larger-model experiment remains under
[cleanup-evaluation](../../cleanup-evaluation/2026-10-30/README.md). Its actual
results are evidence about those frozen runs; this research does not rewrite
them or make the current 9B acquisition pin a production winner.
