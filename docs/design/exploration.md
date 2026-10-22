# Freehand design exploration

October 22, 2026. Sam selected Compact and requested a clickable prototype.

## Confirmed brief

Design for Sam's daily use. Freehand stays in the tray while he dictates into other
applications. Its window manages history, dictionary, and settings. Explore dark
appearance first, using polished image concepts before a clickable prototype.
Replace the cassette-recorder styling. Keep the existing product behavior and stack.

## Incumbent review

This review is based on the current source. No live app screenshot has been captured.

- Brushed panels, bevels, vents, lamps, and an analog meter compete with transcripts.
- Uppercase labels and strong changes between nested surfaces add visual weight.
- The transport panel leads the window even though routine use is tray-first.
- The latest transcript, copy control, and history compete for the same job.
- Repeated action buttons take space in dictionary rows.
- Model details and diagnostics need a clear place within settings.
- The nonactivating recording indicator is a daily interface and belongs in the study.

## Research

Refero's live tools returned NO_SUBSCRIPTION. Use its bundled typography and craft
guidance with the primary references below. No Refero screen or style was retrieved.

- [Windows design](https://learn.microsoft.com/en-us/windows/apps/design/) supplies
  familiar navigation, title-bar conventions, and keyboard-accessible controls.
- [Windows typography](https://learn.microsoft.com/en-us/windows/apps/design/signature-experiences/typography)
  supplies a readable native type hierarchy with Segoe UI Variable.
- [Linear's UI redesign](https://linear.app/now/how-we-redesigned-the-linear-ui)
  supplies an example of reducing chrome and aligning navigation and panels.
- [Raycast for Windows](https://www.raycast.com/windows) supplies a compact utility
  reference for searchable records and focused actions.

The references guide type, hierarchy, and interaction. Their marketing layouts,
claims, and feature sets do not belong in Freehand.

## Grounded candidates

The candidate order reflects relevance to this brief. Impeccable direction seed
1bb00cfa assigned candidate six. Only type, palette, density, and one identifying
detail transfer from these systems. Navigation and controls remain native.

1. Modern wayfinding. Direct labels and clean grouping become Compact's top
   navigation and transcript-first window.
2. Museum information systems. Clear type at multiple reading distances becomes a
   hierarchy for controls, transcript text, and timestamps.
3. Technical reference pages. Consistent text measures organize long transcripts.
4. Contemporary gallery identities. Open spacing separates work without nested panels.
5. Precision product packaging. Clear edges and limited markings inform controls.
6. Contemporary library catalogues. A searchable index and readable detail become
   Index's history browser with a separate reading pane.
7. Digital journal indexes. Date grouping supports quick retrieval across many records.

## Reference locks for the visual options

| Option | Primary reference | Preserve | Signature | Risk |
| --- | --- | --- | --- | --- |
| Index | Digital catalogue, with Linear's aligned panels | Blue-black shell, quiet rules, native sans, separate search/list/reading jobs | Selected history row and transcript share one continuous alignment | Three areas may be excessive for occasional history use |
| Compact | Wayfinding clarity, with Raycast's utility density | Graphite canvas, top navigation, readable transcript text, few visible controls | One selected transcript exposes its actions in place | Long history can become tall |
| Windows native | Windows design and typography | Labeled sidebar, native controls, familiar title bar, consistent spacing | Selected history row uses a restrained Fluent treatment | Less distinctive |

Each option uses the same fictional transcript content. Red identifies recording.
No decorative texture, bevels, analog meter, invented usage statistics, live text
stream, or audio archive is part of these concepts.

The generated images are visual targets for discussion. Their illustrative app
marks are not an approved logo change. A clickable prototype must use real text,
keyboard-accessible controls, and appropriate UI sizing at the actual window size.

## Challenger review

The seed supplied six challengers. Each was considered against audience
identification and product clarity, then declined on both axes for this brief.

| Challenger | Why declined | Discipline retained |
| --- | --- | --- |
| Departure board | Transit imagery and condensed capitals add work | Exact row and timestamp alignment |
| Printed reference | Print conventions restore the unwanted old-fashioned feel | Consistent alignment of controls |
| Dance score | Symbols obscure ordinary history | Visible selection and keyboard focus |
| Record catalogue | Coded labels hide familiar actions | Purposeful space without duplicate labels |
| Bitmap specimen | Pixel lettering contradicts the requested refinement | Deliberate type sizes and weights |
| Ticket wallet | Coupon decoration becomes another period costume | Retain failed work until resolved |

## Current prototype

The [Compact prototype](compact-prototype.md) covers history, dictionary editing,
settings, and recording, processing, and recovery states. Review the interactions
before deciding which parts to implement in Avalonia. The production application
and installed copy are separate later work.
