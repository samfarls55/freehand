---
version: 1
slug: "src-freehand-app-prototypes-compact-index-html"
primary_target: "src/Freehand.App/Prototypes/Compact/index.html"
related_targets: []
---

# Compact clickable prototype

Mode: Operate. A browser simulation of the Windows desktop interface, using sample
data and in-memory state. Sam approved Compact and requested history, dictionary,
settings, and recording states on October 22, 2026.

Approved comp: .impeccable/mocks/decision/compact.png.
The selected composition is locked. Do not generate another direction round.

## Direction contract

THESIS: Make occasional transcript management quick while routine dictation stays
in the tray. Replace the recorder transport panel with readable text and inline actions.

OWN-WORLD: Flat graphite surfaces, near-white native sans text, muted sage selection,
quiet rules, and consistent thin-stroke icons. Red means recording.

STORY: Search and copy past dictations, adjust literal corrections, change settings,
and see recording, processing, recovery, and delivery feedback without losing work.

FIRST VIEWPORT: A slim title bar with Freehand and History, Dictionary, Settings tabs.
Below it, a History heading, search, and a single column of dated transcripts. The
selected transcript exposes Copy and overflow actions. A separate demo strip below
the app drives the floating recording indicator and simulated tray view.

FORM: Compact, first grounded candidate, selected over seed 1bb00cfa's assigned
direction. Preserve the approved image's layout at a practical desktop UI scale.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Scope

One standalone HTML prototype beside Freehand.App, served only on loopback. No
framework, persistence, microphone access, global keyboard hook, or production
changes. Use explicit demo controls for simulation. Browser clipboard Copy may
write the selected sample transcript when the user requests it.

History: search, selection, copy, delete with undo, paging, and empty states.
Dictionary: search, create, edit, enable, delete, correction pairs and reference terms.
Settings: shortcut, insertion, history, login startup, idle timeout, and model details.
Dictation: ready, recording, preparing, transcribing, inserting, success, recovering,
retry, discard, insertion failure, no speech, and microphone failure. Keep a simulated
receiving text field available when the Freehand window is hidden.

Prototype approval does not constitute native implementation or hardware validation.

## Finish evidence

The clickable prototype was completed and reviewed on October 22, 2026. The final
reviewer disposition is ship at prototype scope after resolving keyboard focus
restoration. See `.impeccable/review/compact-verdict.md` and
`docs/design/compact-prototype.md` for verification and limits. The design system
record describes the prototype and does not migrate the native application.
