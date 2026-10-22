# Try the Compact prototype

The approved Compact direction is implemented as a standalone browser prototype at
`src/Freehand.App/Prototypes/Compact/index.html`. It uses sample records and keeps
all changes in memory. Refreshing the page or choosing Reset demo restores the samples.

From the repository root, run:

```powershell
pwsh -File ./scripts/preview-design.ps1
```

Open [the prototype](http://127.0.0.1:65003/). Node.js is the only runtime needed.
The HTML file can also be opened directly, although clipboard access depends on the browser.

## What to try

- Search history, copy a transcript, delete it from its overflow menu, and use Undo.
  Load earlier transcripts to try a longer list.
- Add or edit a dictionary correction. Disable one and try the same sample dictation.
  Reference terms are stored for reference and do not change the simulated transcript.
- Change insertion, history, login startup, the shortcut, and idle timeout in Settings.
  Choices affect only the prototype. Insertion and history settings are captured when
  a dictation starts, so changes during recording apply to the next dictation.
- Choose an Outcome in the demo strip. Start dictation, then Stop recording to move
  through preparing, transcription, and delivery. Transcription fails includes an
  automatic recovery attempt, then retains the recording for Retry or Discard.
- Choose Hide Freehand to try the recording indicator over a simulated foreground
  text field. A successful dictation inserts text there when insertion is enabled.
- Open Sample text to change the next simulated transcript. The default text includes
  `free hand`, which the enabled sample correction changes to `Freehand`.

The prototype does not use the microphone, register a global hotkey, change Windows
startup, read personal history, run Parakeet, or insert text into another application.
Copy writes the selected sample text to the browser clipboard when allowed.

## Design target and scope

Sam selected Compact on October 22, 2026. The approved image is
`.impeccable/mocks/decision/compact.png`. Its top navigation, graphite surfaces,
single text column, and contextual transcript actions are the prototype's target.

This remains a throwaway interaction study. The approved direction is now
implemented in Avalonia; see [Compact in the Windows app](compact-native.md) for
the native behavior, verification, and installation status. Browser verification
establishes the simulation's behavior, not microphone, physical hotkey, or Windows
delivery behavior.

## Verification

Checked in the in-app browser at 1096 by 704 and 690 by 704 pixels on October 22, 2026:

- History search, empty results, Copy, Delete, Undo, and earlier-record loading.
- Dictionary creation, editing, enable switches, and draft preservation across
  navigation, tray restore, and entry-type changes.
- Settings switches and simulated results with insertion and history disabled.
- Successful dictation with the sample correction applied, retained transcription
  failure with Retry and Discard, insertion failure, no speech, and microphone retry.
- Keyboard navigation between tabs, focus restoration after deletion, Undo, and
  loading earlier transcripts, and no horizontal overflow at the tested sizes.

JavaScript and launcher syntax checks passed. The loopback server responds and
returns 404 for files outside the prototype route. These checks describe the
earlier prototype stage. The later native implementation has its own
[verification record](compact-native.md#verification-and-limits).
