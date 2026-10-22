# Packaged Windows implementation

Version 1.0.0 implements the [Windows app PRD](PRD-WINDOWS-APP.md). One desktop app owns
capture, the key, dictation work, delivery, and a hidden speech worker.

## Lifecycle and recovery

`SpeechWorkerClient` reserves accepted work before load, serializes worker operations,
and cancels idle shutdown when work starts. A new recording during shutdown keeps capture
running and waits for the old worker to exit before loading a replacement. A Windows Job
Object kills the child when the owning desktop process exits. The worker also watches its
parent's process handle. Named-pipe traffic uses current-user access, a random handshake
secret, protocol version, stable job IDs, request IDs, and bounded frames.

Startup/load, inference, shutdown, recording, and idle durations are named policies.
Defaults are 30 seconds for worker startup/load, 60 seconds per inference request,
five seconds for graceful shutdown, ten minutes for recording, and five minutes idle.
A deadline stops an unresponsive child. Each accepted dictation gets one automatic
transcription retry. A second failure retains one recording as owned audio segments for Retry or Discard.
Delivery and history are never replayed by transcription retry.

Capture, loading, and decoding overlap. Completed segments of at most 15 seconds decode
sequentially while capture continues. Release waits for capture to drain and for the
remaining segments; correction and delivery still happen once for the entire recording.
Failure discards partial text and retries all retained segments once. Cancelling inference
stops the worker so an obsolete pipe reply cannot affect the next recording.
WASAPI is reopened for each recording. Device and Windows resume events
refresh the hook and capture readiness through platform interfaces. They preserve a
healthy worker and reset failed or unloaded connections. Keyboard callbacks only queue ordered
press/release notifications, and diagnostic storage runs through a bounded background queue.
The fallback sample-rate converter stops when each callback's real input runs out.
Its buffered source must use `ReadFully = false`; padding would keep the drain loop
generating silent output indefinitely. Tests cover float mono, stereo and multichannel
input, PCM16 input, later callbacks after underrun, and output ownership.

## Delivery, preferences, and data

The platform captures the foreground HWND and process identity before recording.
`SendInput` checks that identity before every paced Unicode block. Focus changes and
partial delivery preserve text for Copy. Dictionary correction semantics and shared
vectors are unchanged. Bare dictionary terms carry no recognition-bias promise.

Automatic insertion adds one trailing space to a nonempty corrected transcript unless
it already ends in whitespace. This separates consecutive dictations. The saved transcript
and explicit Copy retain the corrected text; literal trailing spaces, tabs and newlines
from dictionary replacements are preserved. The separator is included in the single
delivery attempt and follows the same focus and retry rules as the transcript.

Live preferences are applied behind an idle reservation. Failed hotkey replacement
rearms the previous key. Insertion and history preferences use the applied snapshot.
Settings and dictionary writes use temporary files and atomic replacement. Unreadable
settings are backed up before replacement. Missing fields in older settings files receive
explicit defaults, including five-minute model idling and login startup, while existing
fields retain their values. Model-path repair can run while a failed recording awaits
Retry. A configuration reservation prevents Retry from racing repair and preserves the
audio and job ID. Other preference changes wait until the failed job resolves.
History reads bounded pages from JSONL,
retains at most 100 cached records, and streams deletion so older pages survive.
Storage errors are reported separately from delivery.

The main window owns presentation; composition owns the key and worker. Closing hides
the window. Tray actions and second launches reuse it. Activation requests arriving before
UI initialization remain in the named event until handlers are attached. Hidden recording
feedback uses a nonactivating panel; hidden and idle meter animation stops. Explicit Quit
confirms discarded audio and awaits owned work off the UI thread.
Background status notifications share one pending UI refresh, preventing an event backlog.

## Installation

`scripts/build-release.ps1` builds the self-contained application and a per-user .NET
installer, embeds a checksummed ZIP payload, and writes the final checksum. The installed
model stays as files rather than being extracted on each launch. The payload includes
the pinned model manifest, known speech fixture, native dependencies, and notices.

Setup extracts into a sibling staging folder and verifies every manifest entry before
stopping the old app. It swaps directories, runs the installed model check and native
self-test, then updates shortcut, uninstall registration, login startup, and repair cache.
The verified replacement remains committed if backup cleanup fails. Bounded filesystem
retries handle Windows retaining executable mappings briefly after process exit. Legacy
installations are stopped without launching an old executable that lacks the shutdown
command. Uninstall removes
application files, startup registration, shortcut, and the dedicated installer cache,
while preserving user settings, dictionary, and transcript history.

The installer builds with the same pinned .NET SDK as the application. The release
includes its runtime and does not require that SDK on the user's machine.

## Review

Two independent code-review passes covered documented standards and PRD behavior against
the migration baseline `99d3356`. The implementation fixed the upgrade cleanup rollback,
startup activation race, cached installer uninstall omission, synchronous hook notification
and log I/O, inline view geometry, unused clipboard delivery code, and duplicate foreground
identity logic. A follow-up pass confirmed those fixes. The additional wrong-type login
preference handling and Quit dialog token were corrected after that pass.
The final review at `6de3c6b` confirmed migrated preference defaults, worker preservation
during device notifications, and retained-audio model repair, with no further material findings.

Verification commands, measured targets, packaging smoke checks, and the remaining physical
hardware session are recorded in [WINDOWS-VERIFICATION.md](WINDOWS-VERIFICATION.md).
