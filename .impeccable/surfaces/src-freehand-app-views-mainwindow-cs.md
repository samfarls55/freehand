---
version: 1
slug: "src-freehand-app-views-mainwindow-cs"
primary_target: "src/Freehand.App/Views/MainWindow.cs"
related_targets: []
---

# Freehand logo-aligned native interface

Mode: Operate. Target: `src/Freehand.App/Views/MainWindow.cs` and related Avalonia views, the dictionary editor, the recording indicator, the update panel, the quit dialog, and tray text.

## Direction contract

THESIS: The app should look like it came from the same hand as its logo, a soft cream cursive "f" on warm black. It rejects the generic graphite-and-sage utility look and its filler headings, counts, and helper lines.

OWN-WORLD: Logo black #12110F ground, warm raised panel #1C1A17, cream #E3DCCB for primary pills, toggles, focus, and selection, warm ink #EEE8DC, warm muted #A39B8E. Pill buttons, 10-DIP fields, 14-DIP groups. The selected tab carries a hand-drawn swash taken from the f's crossbar. Red still means recording, and amber still means attention.

STORY: Sam opens Freehand from the tray to copy a transcript, fix a phrase, or change a preference. The f mark and the cream accents say Freehand without any label.

FIRST VIEWPORT: The real f mark sits at the left gutter. Centered text tabs have a cream swash under the selected one. There is no page title. Search fills the first row, with that tab's actions beside it. Transcript rows follow. The footer has a centered Record pill and the hotkey as a keycap at the right.

FORM: Retheme of the approved Compact structure. seed: none (pinned) "It's currently not consistent with the logo and looks a bit generic and AI-generated, including too many subtitles and filler text"; Sam chose "Retheme + cut copy" and "Cream from the logo".

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Scope

Use the existing stores and engine. Do not change dictation, delivery, hotkey, or model behavior. Keep the strings the tests depend on.
