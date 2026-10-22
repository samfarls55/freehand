# Compact in the Windows app

The approved Compact design is implemented in Freehand's Avalonia interface.
Sam selected the direction on October 22, 2026. The
[decision image](../../.impeccable/mocks/decision/compact.png) and
[prototype](../../src/Freehand.App/Prototypes/Compact/index.html) preserve the
approval evidence. [DESIGN.md](../../DESIGN.md) records the native tokens and
component rules. The [native direction contract](../../.impeccable/surfaces/src-freehand-app-views-mainwindow-cs.md)
records this implementation's scope.

## Native implementation

The main window uses a graphite background, waveform mark, centered text tabs,
readable transcript rows, and restrained sage actions. Red identifies recording;
amber identifies attention and recovery. Disabled actions have a visible inactive
treatment. Windows retains the title bar and window controls.

| Area | Native implementation |
| --- | --- |
| Tokens and controls | DesignTokens.cs, CompactTheme.cs, and Panels.cs |
| Main window | MainWindow.cs owns navigation, recording controls, and engine feedback |
| History | TranscriptionsView.cs uses the persistent store, search, Copy, deletion, and bounded pages |
| Dictionary | DictionaryView.cs uses the existing dictionary file and an owner-modal editor |
| Settings | SettingsView.cs shares persisted controls between the main tab and SettingsWindow.cs |
| Tray dictation | StatusIndicator.cs, Lamp.cs, and DictationActivity.cs show nonactivating activity and attention |

All source paths in this table are under `src/Freehand.App`. Views and shared
layout helpers are in `Views`, tokens and theme are in `Design`, and activity
controls are in `Controls`. App.axaml requests the dark Fluent theme.

The main window defaults to 880 by 700 DIPs and supports a minimum of 720 by 520.
A DIP is an Avalonia device-independent pixel. Windows scales it to physical
pixels. Native lists and settings scroll within those constraints; browser
breakpoints and the prototype's custom window controls do not apply.

The prototype's inline editor becomes an owner-modal native editor. Its sample
history loader becomes Older and Newer controls over real store pages. The
native implementation preserves the existing on-screen Record action and
configured shortcut label. It does not add the prototype's simulated Undo,
receiving field, or demo outcome controls.

The header waveform, search icon, and overflow dots are authored vector geometry.
The redesign adds no shipping raster assets. The existing application and tray
icon remain in use. Generated decision images and native captures are design
evidence, outside the application UI assets.

## Behavior preserved

The views use the existing history, dictionary, settings, and dictation services.
Right Ctrl remains the default. Closing the main window hides it; explicit Quit
shuts the app down. The tray indicator stays nonactivating and follows the
selected display's working area and scaling.

Retained recordings keep Retry and Discard. Failed text insertion exposes the
transcript and Copy. Disabling history still leaves the latest transcript
available. Settings continue through the existing preference coordinator, and
changes made during dictation apply when it finishes.

This implementation changes no speech engine, capture, keyboard hook, SendInput
delivery, literal dictionary semantics, shared correction vectors, or pinned
dependency versions. Saved terms remain reference entries; correction pairs
change recognized text through the existing dictionary contract.

## Try the native app

Quit the installed copy from its tray menu, then run from the repository root:

```powershell
pwsh -File ./scripts/dev.ps1
```

The development profile and model are prepared. This command opens the source
build with separate settings, dictionary, history, and logs. Try History,
Dictionary, Settings, closing to the tray, and dictation into a foreground text
field. Only one copy can own the global key. The full workflow is in
[DEVELOPMENT.md](../DEVELOPMENT.md).

## Verification and limits

After syncing with main's performance updates on October 22, 2026:

- The Release build with `--no-incremental -warnaserror` passed with zero warnings
  and errors.
- All 122 .NET tests passed, covering 68 Core, 24 Dictionary, 6 Windows, and 24 App tests.
- All 27 deployment-script tests passed, including the pinned Pester bootstrap.
- Installer packaging and the published executable's `--selftest` passed.
- The [independent finish review](../../.impeccable/review/native-verdict.md)
  resolved its waveform, amber feedback, and disabled-action findings and returned
  `disposition: ship`.

The branch includes main through `78511e7`. Compact retains main's queued UI
feedback, Parakeet TDT 110M configuration, and spacing between consecutive
dictations. Settings now uses the model resolver's bundled directory and names
the current model. A UI regression test checks bundled and custom model paths.
PR review also added coverage for copying results on every tab when insertion is
disabled, and keeping dictionary keyboard focus on the same entry when replacement
text is shared. The cancellation test uses caller cancellation without racing an
unrelated inference deadline.

The [native captures](../../.impeccable/review/native) use Avalonia headless Skia
rendering and synthetic data. History, dictionary, settings, and recording are
captured at 880 by 700 and 720 by 520. Additional captures cover recovery, failed
delivery, the dictionary editor, and floating Recording, Transcribing, and
AwaitingRetry states. The floating indicator also has light-system-theme checks;
the product itself requests dark appearance. Captures exclude OS window chrome.

These checks establish source, layout, state presentation, regression tests, and
published startup. They do not establish physical microphone capture, a physical
hotkey press, or text delivery into a foreground application. Those hands-on
checks have not been repeated for this design change.

The Compact work is committed locally. The installed application has not been
updated, and no push or GitHub publication occurred. Use the development profile
to try the source, and follow [DEVELOPMENT.md](../DEVELOPMENT.md) for verification,
local installation, and publication. Those remain separate operations.
