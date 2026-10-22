---
name: Freehand Compact
description: Native Windows dictation interface, implementing the approved Compact direction.
colors:
  chassis: "#1C1F20"
  panel: "#232728"
  cap: "#252A2A"
  seam: "#343A39"
  ink: "#F1F3F2"
  muted: "#AFB6B3"
  record: "#F45B55"
  accent: "#B5C9BC"
  accent-ink: "#18231C"
  attention: "#E3BD7B"
typography:
  title:
    fontFamily: "Segoe UI Variable, Segoe UI, sans-serif"
    fontSize: "30px"
    fontWeight: 600
  section:
    fontFamily: "Segoe UI Variable, Segoe UI, sans-serif"
    fontSize: "17px"
  transcript:
    fontFamily: "Segoe UI Variable, Segoe UI, sans-serif"
    fontSize: "16px"
    lineHeight: "27px"
  body:
    fontFamily: "Segoe UI Variable, Segoe UI, sans-serif"
    fontSize: "15px"
  control:
    fontFamily: "Segoe UI Variable, Segoe UI, sans-serif"
    fontSize: "14px"
  label:
    fontFamily: "Segoe UI Variable, Segoe UI, sans-serif"
    fontSize: "13px"
  timer:
    fontFamily: "Cascadia Mono, Consolas, monospace"
    fontSize: "13px"
rounded:
  chip: "2px"
  field: "6px"
  control: "7px"
  panel: "8px"
  status: "22px"
spacing:
  hair: "2px"
  tight: "4px"
  snug: "8px"
  base: "12px"
  roomy: "16px"
  wide: "24px"
  panel: "32px"
  gutter: "44px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  button-secondary:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  button-disabled:
    backgroundColor: "{colors.cap}"
    textColor: "{colors.muted}"
    rounded: "{rounded.control}"
  search:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.field}"
  navigation-tab:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    typography: "{typography.control}"
  transcript-row:
    textColor: "{colors.ink}"
    typography: "{typography.transcript}"
    padding: "16px 0"
  settings-group:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.panel}"
    padding: "8px 16px"
  feedback:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.panel}"
    padding: "16px"
  recording-indicator:
    backgroundColor: "{colors.chassis}"
    textColor: "{colors.ink}"
    rounded: "{rounded.status}"
    width: "208px"
    height: "44px"
---

# Design system: Freehand Compact

## Overview

Compact is Freehand's native Avalonia design. A graphite window, centered text
tabs, readable transcript rows, and restrained sage actions support a daily,
tray-first dictation workflow. Windows retains its title bar and window controls.
The application requests the dark Fluent theme.

Sam selected Compact on October 22, 2026. The approved
[decision image](.impeccable/mocks/decision/compact.png) and
[browser prototype](src/Freehand.App/Prototypes/Compact/index.html) record that
approval. The cassette and field-recorder appearance is the confirmed
anti-reference. The prototype remains a throwaway interaction study.

This file describes the implemented native system. Apply these values through
[DesignTokens.cs](src/Freehand.App/Design/DesignTokens.cs) and
[CompactTheme.cs](src/Freehand.App/Design/CompactTheme.cs). Code owns rendering;
keep this specification and [.impeccable/design.json](.impeccable/design.json) in
sync with it. Native evidence and adaptations are recorded in
[compact-native.md](docs/design/compact-native.md).

## Colors

Sage identifies selection and primary actions. Neutral graphite fills separate
controls and settings groups without giving every row its own card.

| Token | Use |
| --- | --- |
| chassis | Main window, dialogs, and floating dictation indicator |
| panel | Input backgrounds, ordinary buttons, settings groups, and feedback panels |
| cap | Ordinary button hover, pressed, and disabled fills; selected editor type |
| seam | One-DIP dividers and field borders |
| ink | Main text and waveform mark |
| muted | Metadata, inactive tabs, quiet actions, and placeholders |
| accent | Primary actions, selected tab underline, text selection, and processing dots |
| accent-ink | Text on sage actions and selected text |
| record | Active recording dot and main-window recording label |
| attention | Recovery, capture failure, empty speech, delivery failure, and validation |

Pair state color with text and an applicable action. Attention feedback in the
main window has an amber border and message. Ordinary transcript availability
does not receive that attention treatment.

## Typography

Use the Windows UI family for text and controls. The monospace family is for the
main recording timer. Titles are semibold, the brand and selected tabs are
semibold, and transcript text is regular with an explicit line height.

The frontmatter uses `px` strings for portability. In this native specification,
they serialize Avalonia device-independent pixels, or DIPs. Windows display
scaling determines the physical pixels. These values do not import the browser
prototype's CSS dimensions or breakpoints.

Preserve transcript line breaks and wrapping. Use sentence case. Keep field
labels, state feedback, and recovery instructions that explain an action. Cut
taglines and labels that repeat what the layout already shows.

## Layout

The main window defaults to 880 by 700 DIPs with a 720 by 520 minimum. The header
places a waveform and Freehand at left and History, Dictionary, and Settings tabs
at the center. Its selected tab has a three-DIP sage underline. The native title
bar sits above this application header.

Content has 44-DIP side gutters. Page headings have 32 DIPs above and 24 below;
search has 24 DIPs below. History and dictionary rows use a single text column
with always-visible actions at the right. Their lists scroll while headings,
search, pagination or file access, feedback, and the recording footer remain
reachable. Settings scroll as one column of groups. There are no browser-style
responsive breakpoints in the native layout.

The footer centers the Record action and shows the configured push-to-talk key
at the right. The tray Settings window reuses SettingsView in a 640 by 700 window,
with a 540-DIP minimum width. The dictionary editor is a 500-DIP-wide owner-modal
window whose height follows its content.

## Elevation & Depth

The application draws flat fills and one-DIP seams. It adds no custom shadow to
transcript rows, settings groups, feedback, or the floating indicator. Native
Fluent templates and Windows own their standard focus, menu, and window behavior.
Do not copy the browser prototype's outer-window shadows into the native app.

## Shapes

Use the frontmatter radii for fields, buttons, groups, and the status capsule.
Transcript and dictionary rows have square edges with a bottom divider. The
header's five-stroke waveform is authored vector geometry, 24 DIPs with a 1.5-DIP
rounded stroke. Search and overflow controls also use vector geometry. This
redesign adds no shipping raster assets; the existing app and tray icon remain.

## Components

Buttons have a 38-DIP minimum height. Primary buttons retain sage when hovered or
pressed. Ordinary and quiet buttons use the cap fill in those states. Disabled
buttons use the cap fill, muted text, 45% opacity, and native disabled semantics.
Do not leave an invalid Save entry or unavailable Record action looking active.

TextBox controls have panel fills, seam borders, muted placeholders, and sage
focus borders and carets. Selected text uses sage with dark text. Fluent controls
provide input, toggle, combo box, numeric input, menu, and keyboard behavior.
Keep icon buttons and unlabeled toggles named for accessibility.

History uses selectable transcript text, local dates and times, Copy, and an
overflow menu. Copy briefly becomes Copied. Older and Newer navigate the existing
bounded store pages. Deletion uses the existing store directly; the prototype's
Undo simulation is not part of this implementation.

Dictionary rows show a saved term or correction pair beside enable, Edit, and
overflow actions. The modal editor switches between Term and Correction without
discarding the current fields. Save stays disabled until the required fields
contain text. Warnings use amber. Settings use the same native view from the main
tab and tray window, including deferred preferences and model details.

The floating dictation indicator remains nonactivating and outside the taskbar.
It is 208 by 44 DIPs during activity and widens to 288 DIPs for attention. Recording
has a red dot and five bars driven by microphone levels. Processing has three
sage dots advanced every 180 milliseconds. This timer runs only while the
indicator is visible and processing. Idle attention notices last three seconds;
retained-recording recovery stays available in Freehand. Keep monitor-aware,
scaling-aware placement above the work area edge.

The main window presents Retry and Discard for retained audio, Retry for capture
failure, and Copy when a transcript is available for recovery. It also exposes
the latest transcript when history is disabled. Keep these actions connected to
the existing engine.

## Do's and Don'ts

- Do keep routine dictation in the tray and preserve the receiving app's focus.
- Do use native tokens and Fluent controls when adding or changing a view.
- Do pair red recording and amber attention with explicit text.
- Do preserve real history, dictionary, settings, and recovery behavior.
- Don't add recorder textures, bevels, decorative labels, or browser demo controls.
- Don't treat a headless capture as hardware validation, installation, or publication.
