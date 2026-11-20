---
name: Freehand
description: Native Windows dictation interface in the logo-aligned retheme of the Compact structure.
colors:
  chassis: "#12110F"
  panel: "#1C1A17"
  cap: "#27241F"
  seam: "#2F2B26"
  ink: "#EEE8DC"
  muted: "#A39B8E"
  record: "#F0645A"
  accent: "#E3DCCB"
  accent-ink: "#12110F"
  attention: "#E4B66C"
typography:
  empty:
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
  group:
    fontFamily: "Segoe UI Variable, Segoe UI, sans-serif"
    fontSize: "14px"
    fontWeight: 600
  label:
    fontFamily: "Segoe UI Variable, Segoe UI, sans-serif"
    fontSize: "13px"
  timer:
    fontFamily: "Cascadia Mono, Consolas, monospace"
    fontSize: "13px"
rounded:
  chip: "2px"
  field: "10px"
  panel: "14px"
  control: "19px"
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
    height: "38px"
  button-secondary:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
    height: "38px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  button-quiet-hover:
    backgroundColor: "{colors.cap}"
  button-disabled:
    backgroundColor: "{colors.cap}"
    textColor: "{colors.muted}"
    rounded: "{rounded.control}"
  segment-selected:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.control}"
  search:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.field}"
    height: "38px"
  navigation-tab:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    typography: "{typography.control}"
  navigation-tab-selected:
    textColor: "{colors.ink}"
  tab-swash:
    backgroundColor: "{colors.accent}"
    width: "46px"
  keycap:
    textColor: "{colors.muted}"
    typography: "{typography.label}"
    rounded: "{rounded.field}"
    padding: "4px 8px"
  record-pill:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    rounded: "{rounded.status}"
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

# Design system: Freehand

## Overview

**Creative North Star: "From the same hand as the mark"**

Freehand's native Avalonia interface looks like it came from the same hand as
its logo: a soft cream cursive f on warm black. The window is the logo's black,
raised surfaces are a half-step warmer, and one cream accent carries every
selection, primary action, toggle, and focus. Controls are soft pills. The f
mark sits at the left of the header, and a filled swash cut from the f's
crossbar sits under the selected tab. Windows keeps its title bar and window
controls, and the application requests the dark Fluent theme.

The layout carries the meaning, so the copy stays short. There are no page
titles, counts, entry-type labels, or helper lines. Search opens each tab, with
that tab's actions beside it, and transcript text takes the remaining space.
Red still means recording and amber still means attention.

History. Sam selected the Compact structure on October 22, 2026. The approved
[decision image](.impeccable/mocks/decision/compact.png) and
[browser prototype](src/Freehand.App/Prototypes/Compact/index.html) record that
approval; the prototype remains a throwaway interaction study. On November 19,
2026, Sam approved a retheme of that structure toward the logo ("Retheme + cut
copy", "Cream from the logo"), which replaced the graphite and sage palette,
the waveform and wordmark, and the page headings. Code classes keep the Compact
name (`CompactTheme`, `compact-*` captures). The cassette and field-recorder
appearance remains the confirmed anti-reference.

This file describes the implemented native system. Apply these values through
[DesignTokens.cs](src/Freehand.App/Design/DesignTokens.cs) and
[CompactTheme.cs](src/Freehand.App/Design/CompactTheme.cs). Code owns rendering;
keep this specification and [.impeccable/design.json](.impeccable/design.json) in
sync with it. Earlier native evidence and adaptations are recorded in
[compact-native.md](docs/design/compact-native.md); retheme captures are in
`.impeccable/review/logo/`.

**Key Characteristics:**
- Warm black ground with warm cream ink; no cool grays.
- One cream accent, used for selection, primary actions, toggles, focus, and the swash.
- Pill buttons, 10-DIP fields, 14-DIP groups.
- The f mark is the only brand element; there is no wordmark.
- No page titles or filler copy; search is the first row.

## Colors

The palette is the logo's: warm black, a slightly raised warm panel, and cream.

| Token | Use |
| --- | --- |
| chassis | Main window, dialogs, floating dictation indicator, and toggle knobs when on |
| panel | Search and text fields, ordinary buttons, the Record pill, settings groups, and feedback |
| cap | Ordinary and quiet button hover, pressed, and disabled fills; field hover |
| seam | One-DIP header and row dividers, field borders, the keycap outline, and the indicator outline |
| ink | Main text, the selected tab, transcripts, and recording-level bars |
| muted | Timestamps, inactive tabs, quiet actions, placeholders, group headings, toggles when off, and the unlit lamp |
| accent | Primary pills, selected segments, toggle fills, focus borders, carets, text selection, the tab swash, and processing dots |
| accent-ink | Text on cream fills and selected text |
| record | Active recording lamp and the main-window recording label |
| attention | Recovery, capture failure, empty speech, delivery failure, model problems, and validation |

**The One Cream Rule.** Cream is the only accent. Anything chosen, primary, or
focused is cream; everything else is warm black, warm panel, ink, or muted.

**The Status Pair Rule.** Red and amber appear only as state, always paired with
text and, where one exists, an action. Attention feedback in the main window has
a one-DIP amber border and amber message; ordinary transcript availability has
no border.

## Typography

Use the Windows UI family for text and controls. The monospace family is for the
main recording timer. There is no display or title level: the largest text is
the 17-DIP empty-state line, and transcripts at 16 DIPs with a 27-DIP line height
are the reading text. The selected tab is semibold. Settings group headings are
14-DIP semibold in muted, inset 16 DIPs to align with the group's content.
Timestamps and field labels use the 13-DIP label size in muted.

The frontmatter uses `px` strings for portability. In this native specification,
they serialize Avalonia device-independent pixels, or DIPs. Windows display
scaling determines the physical pixels.

**The No Filler Rule.** Use sentence case and keep text that names a control,
reports a state, or explains a recovery action. Cut page titles, counts,
entry-type labels, taglines, and helper lines that repeat what the layout shows.

## Layout

The main window defaults to 880 by 700 DIPs with a 720 by 520 minimum. The header
places the 30-DIP f mark at left, inset 40 DIPs, and History, Dictionary, and
Settings tabs at the center with 4 DIPs between them. A one-DIP seam closes the
header. The native title bar sits above it.

Content has 44-DIP side gutters. Each list tab opens with its search row: 24 DIPs
above, 12 below, the field filling the width and the tab's actions docked right
with 8 DIPs between them. History puts its overflow menu there; Dictionary puts
Add entry and an overflow menu holding Open dictionary.txt. Rows follow in a
single text column with always-visible actions at the right. Older and Newer sit
right-aligned under the list and appear only when another page exists. Settings
scroll as one column of groups, 24 DIPs apart, with 24 DIPs above and below.

The footer centers the Record pill and shows the push-to-talk key as a keycap at
the right. The tray Settings window reuses SettingsView in a 640 by 700 window,
with a 540-DIP minimum width. The dictionary editor is a 500-DIP-wide owner-modal
window whose height follows its content. The quit dialog is 440 DIPs wide with
its actions right-aligned. There are no responsive breakpoints.

## Elevation & Depth

The application is flat. Depth is one tonal step (chassis to panel) and one-DIP
seams. It adds no custom shadow to rows, groups, feedback, the Record pill, or the
floating indicator. Native Fluent templates and Windows own their standard focus,
menu, and window behavior.

## Shapes

Buttons are pills (radius half the 38-DIP control height). Fields and the keycap
use 10 DIPs, settings groups and feedback 14 DIPs, and the Record pill and
floating indicator are full capsules. Transcript and dictionary rows are square
with a bottom seam. Recording-level bars use the 2-DIP chip radius.

The f mark is a shipping raster, `Assets/brand-mark.png`, derived from
`Assets/app-icon.png` and drawn at 30 DIPs with high-quality interpolation. The
tab swash is authored vector geometry taken from the f's crossbar: a filled cream
stroke 46 DIPs wide that tapers at the left and ends in a rounded terminal at the
right. Search, overflow, and the recording-level bars are also vector geometry.

**The Crossbar Rule.** The swash marks the selected tab and nothing else. It is
filled, not stroked, and never becomes a generic underline.

## Components

Buttons have a 38-DIP minimum height and pill corners. Primary buttons are cream
with warm black text and stay cream when hovered or pressed. Ordinary buttons use
the panel fill and quiet buttons are transparent with muted text; both use the cap
fill when hovered or pressed. Disabled buttons use the cap fill, muted text, 45%
opacity, and native disabled semantics. Do not leave an invalid Save entry or
unavailable Record action looking active. In the quit dialog, Keep running is
primary and Discard and quit is quiet.

TextBox controls have panel fills, seam borders, muted placeholders, a cap fill
and muted border on hover, and cream focus borders and carets. Selected text is
cream with warm black text. Toggles are cream with a warm black knob when on and
an outlined muted track when off. Fluent controls provide input, toggle, combo
box, numeric input, expander, menu, and keyboard behavior. Keep icon buttons and
unlabeled toggles named for accessibility.

History rows show a muted timestamp, selectable transcript text, a quiet Copy,
and an overflow menu. Copy briefly becomes Copied. Deletion uses the existing
store directly.

Dictionary rows show the entry at transcript size. A correction shows the heard
phrase and arrow in muted and the written phrase in ink; a saved term shows only
the written phrase. Disabled entries drop to 50% opacity. Each row has an enable
toggle, Edit, and an overflow menu. The modal editor's Term and Correction choice
is a segmented pair whose selected segment is cream; switching keeps the current
fields. Save stays disabled until the required fields contain text. Warnings use
amber.

Settings groups are panel cards with a muted group heading above. Rows place the
label at left and the control at right. Model status sits right-aligned
on the model's name row, muted when healthy and amber when attention is needed,
and model details collapse into a Details expander.

The push-to-talk field is a bordered pill displaying the saved combination.
Selecting it records simultaneous keys and saves after every key is released.
Cancel appears beneath the field during capture, so Escape and Tab can be bound.
Long combinations wrap in the field. The footer keycap truncates long
combinations and exposes the full shortcut on hover. Capture pauses dictation and
cancels when the view or window closes or hides.

The Record pill holds the lamp, the label, live level bars, and the monospace
timer. The lamp is muted when idle and red while recording, and the label turns
red while recording.

The floating dictation indicator remains nonactivating and outside the taskbar.
It is a chassis capsule with a seam outline, 208 by 44 DIPs during activity, and
widens to 288 DIPs for attention. Recording has a red lamp and five ink bars
driven by microphone levels. Processing has a cream lamp and three cream dots
advanced every 180 milliseconds; this timer runs only while the indicator is
visible and processing. Attention uses an amber lamp. Idle attention notices last
three seconds; retained-recording recovery stays available in Freehand. Keep
monitor-aware, scaling-aware placement above the work area edge.

The main window presents Retry and Discard for retained audio, Retry for capture
failure, and a primary Copy when a transcript is available for recovery. It also
exposes the latest transcript when history is disabled. Keep these actions
connected to the existing engine.

## Do's and Don'ts

- Do keep routine dictation in the tray and preserve the receiving app's focus.
- Do use native tokens and Fluent controls when adding or changing a view.
- Do use cream for every selected, primary, or focused state, and nothing else.
- Do pair red recording and amber attention with explicit text.
- Do preserve real history, dictionary, settings, and recovery behavior.
- Don't add page titles, counts, type labels, taglines, or helper lines.
- Don't add a wordmark or a second brand mark beside the f.
- Don't reintroduce graphite, sage, or other cool neutrals.
- Don't add recorder textures, bevels, decorative labels, or browser demo controls.
- Don't treat a headless capture as hardware validation, installation, or publication.
