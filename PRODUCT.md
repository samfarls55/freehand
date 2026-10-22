# Freehand

<!-- impeccable:product-schema 1 -->

## Platform

Windows desktop, built with C#/.NET 10 and Avalonia.

Impeccable's platform schema does not include Windows desktop. This is a native
desktop application. Do not apply web, iOS, or Android platform assumptions to it.

## Users

Design for Sam as a daily user first. Other Windows users are a later audience.
Sam values simple processes, clear controls, and fewer steps between speaking and
getting text into the application he is using.

## Product purpose

Hold a global push-to-talk key, speak, and release to insert the transcript at the
caret in another application. Freehand handles recording, local transcription,
dictionary corrections, and delivery.

## Operating context

Freehand stays in the Windows tray during normal use. Its main window is for
transcript history, dictionary entries, and settings. The recording indicator is
part of everyday use and must provide feedback without taking focus from the
application receiving the text.

The default push-to-talk key is Right Ctrl. Closing the main window keeps Freehand
running. Explicit Quit shuts it down.

## Capabilities and constraints

- Local English speech recognition uses Parakeet through sherpa-onnx on the CPU.
  The installer includes the speech model and runtime. Dictation works offline.
- Transcripts appear after the user releases the key. The current product does not
  provide a live text stream while the user speaks.
- History supports search, copying, deletion, and bounded pages.
- The dictionary supports saved terms and explicit correction pairs. Bare terms
  do not currently influence recognition. Preserve the shared correction contract.
- Settings include the hotkey, automatic text insertion, history, Windows login
  startup, and the idle timeout for releasing the speech model.
- Preserve recordings that can be retried and transcripts that could not be
  inserted. Recovery must provide clear Retry, Discard, or Copy actions.
- Keep capture, keyboard hooks, and SendInput delivery in the Windows platform
  project. A visual redesign does not change the speech or delivery architecture.
- Keep the existing stack and pinned dependencies. Production interface styling
  remains centralized in the design tokens.

## Brand commitments

The product is named Freehand. Sam requested a refined replacement for the current
recorder appearance on October 22, 2026. The cassette and field-recorder styling is
an anti-reference for this exploration. That request supersedes earlier directions
to retain that appearance.

Cut taglines, helper text, and redundant secondary labels. Make the layout explain
the controls. Keep necessary field labels, status feedback, and recovery actions.

Sam selected Compact on October 22, 2026 after the image concepts and browser
prototype. The native implementation now uses its dark graphite window, centered
text tabs, single transcript column, and inline actions. Windows retains its title
bar and native controls. DESIGN.md records the implemented visual system.

## Evidence on hand

- README.md describes the shipped workflow and current capabilities.
- docs/PRD-WINDOWS-APP.md records the dictation and recovery requirements. Its
  instructions to retain the recorder appearance predate this redesign request.
- docs/DEVELOPMENT.md describes development, verification, local installation,
  and publication as separate operations.
- src/Freehand.App/Views contains the main window, history, dictionary, settings,
  dictionary editor, and recording indicator.
- src/Freehand.App/Design/DesignTokens.cs and CompactTheme.cs centralize the native
  Compact palette, typography, geometry, and Fluent control styling. SettingsView
  is shared by the main Settings tab and tray settings window.
- .impeccable/mocks/decision/compact.png and the browser prototype record Sam's
  approved direction. docs/design/compact-native.md explains the native adaptations.
- .impeccable/review/native contains Avalonia headless Skia captures with synthetic
  records. They establish native presentation, without OS chrome or hardware proof.
- .impeccable/review/native-verdict.md records the independent finish review and
  the resolved waveform, amber feedback, and disabled-action fixes.
- Sam confirmed the primary audience and tray-first workflow in this conversation.

## Product principles

- Keep routine dictation in the background and preserve the user's focus.
- Make recording, processing, and failures distinguishable at a glance.
- Make history, dictionary changes, and settings easy to find when needed.
- Preserve recoverable work and provide a concrete action when something fails.
- Prefer a simpler solution that improves use, maintenance, and agent navigation.

## Implementation status

Compact is implemented in the native source and passed the Release build, 91 tests,
installer packaging, and the published executable's self-test on October 22, 2026.
The installed copy has not been updated, and no GitHub publication occurred.
Physical microphone, hotkey, and delivery checks remain hands-on validation.

The browser prototype remains a historical simulation with sample data. Its Undo
and simulated receiving field do not define native capabilities. Installation and
publication follow docs/DEVELOPMENT.md as separate operations.
