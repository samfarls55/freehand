# Freehand Compact native implementation

Mode: Operate. Target: `src/Freehand.App/Views/MainWindow.cs` and related Avalonia views.

## Direction contract

THESIS: Freehand is a tray-first dictation utility. Its main window manages history, dictionary, and settings through a compact single-column workspace.

OWN-WORLD: Port the approved browser prototype into native Avalonia controls. Graphite window, Segoe UI, near-white transcripts, sage selection underline and primary actions. Flat rows with inline Copy and overflow. Red identifies recording. Amber identifies recovery.

STORY: Sam returns to copy a transcript, correct a recurring phrase, or change a preference. Global dictation continues through the existing engine and platform services.

FIRST VIEWPORT: Slim brand and centered text tabs. A 30 DIP page title above a search field. Readable transcript rows with dates, inline actions, and subtle dividers. A small bottom recording control preserves the existing on-screen action. Windows retains its title bar. Native minimum is 720 by 520; default is 880 by 700. Scrolling preserves access at smaller heights.

FORM: Compact, approved by Sam from the original direction round, seed 1bb00cfa. This is an implementation of the approved prototype, not another direction round. The prototype and decision comp remain the visual references.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Scope

Use real stores and settings. Preserve Right Ctrl, tray lifecycle, nonactivating indicator, preference deferral, model resolution, literal dictionary behavior, retries, retained audio, and text delivery. No dependency, engine, speech, capture, hook, or injection changes. No installed update or GitHub publication.

## Evidence

Native captures under `.impeccable/review/native/` come from Avalonia headless Skia rendering. The test fixtures are synthetic. Captures prove native layout and presentation; they do not prove a physical microphone, hotkey, or delivery to another application.
