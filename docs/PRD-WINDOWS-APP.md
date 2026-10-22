# Freehand for Windows: packaged dictation app

Date: October 9, 2026

Owner: Sam

Purpose: Define the complete implementation needed before Sam's final hands-on test.

## 1. What I want to be able to do

I want to install one Windows application, open it from my taskbar, and dictate into the application I'm using. I should be able to leave it in the background without Parakeet taking roughly 2 GB of RAM for the entire day.

The app should handle its own model, startup, memory use, and recovery. I don't want to start a service, open a terminal, manage another application, or check whether Parakeet is running before I speak. If something fails, the app should recover when it can and give me a useful next step when it can't.

Speed matters. The solution should start recording when I press the hotkey, load the model while I'm speaking, and keep the model available during a session of repeated dictations. After five minutes without activity, it should release the model's memory.

Deliver this as one complete implementation and one packaged build. Complete the engineering checks and fix failures before handing the app to me. My hands-on testing happens at the end.

## 2. Scope and existing baseline

Keep the current C#/.NET 10 and Avalonia application. Use the existing Windows platform layer and Parakeet TDT v2 int8 model through sherpa-onnx. This release targets Windows x64 on Sam's computer. Keep the existing architecture compatible with a later Windows ARM64 package.

The existing source already has audio capture, a global push-to-talk hotkey, local speech recognition, dictionary corrections, transcript history, text insertion, and a recorder interface. The work is to connect these into a reliable application and package the full result.

The source review identified these gaps:

| Existing behavior | Required change |
|---|---|
| Model loading starts after the hotkey is released. | Start loading on press, alongside audio capture. |
| The loaded recognizer remains until app shutdown. | Release it after an idle timeout. |
| Native loading and inference run inside the app. | Move them into a worker owned by the app. |
| Model status checks whether files exist. | Report installation, loading, readiness, and failure accurately. |
| Closing the window destroys it, while the tray tries to reopen the same window. | Hide and restore the window correctly. |
| There is no single-instance coordination or Windows login startup. | Add both, with one owner of the hotkey and worker. |
| Hotkey changes are saved but take effect after restart. | Apply changes safely without restarting the app. |
| The text-insertion setting is saved but ignored. | Respect the setting on every dictation. |
| Several capture, loading, and insertion failures have no useful user feedback. | Handle failures and preserve recoverable work. |
| Processing time excludes model loading and text delivery. | Measure the wait the user actually experiences. |
| Publishing produces a directory whose dependencies and model need to be kept together. | Build an installer containing everything needed to run. |

The existing installed executable passed its startup self-test on October 8. That check did not establish live microphone capture, physical hotkey behavior, or successful delivery into another app. The current machine has no SDK listed by `dotnet --list-sdks`, so the implementation work includes setting up the pinned development SDK.

This release excludes macOS work, an Electron rewrite, cloud transcription, GPU inference, LLM rewriting, command mode, and a general interface redesign. Keep the existing dictionary correction contract and recorder design.

## 3. One application, with an internal speech worker

The user sees one installed application, one tray icon, and one settings window. The app owns a hidden child process for speech recognition. That process is an implementation detail and has no separate installation, startup entry, window, or user controls.

Prefer running the installed executable in an internal worker mode, such as `--speech-worker`, to avoid another independently distributed executable. Enter that mode before starting Avalonia or enforcing the desktop app's single-instance behavior.

The main process owns the hotkey, microphone capture, recording buffers, dictionary correction, history, and text delivery. The worker owns native model loading and inference. Keeping recording in the main process lets the app recover from a worker failure without losing the audio it already captured.

Use a local named pipe or equivalent local IPC connection, with explicit request IDs, protocol version, readiness acknowledgments, errors, and shutdown messages. Limit access to the current user and the worker launched by this app. Do not expose a network port or depend on a localhost HTTP service.

Allow one desktop instance and at most one speech worker. Serialize native loading and inference. A second launch should activate the existing window and exit. Worker mode must bypass that activation path.

Gracefully stop the worker when idle or quitting. Use bounded termination if it stops responding. Ensure the worker exits if the parent app crashes or disappears, since Windows does not automatically stop child processes when their parent exits. Windows releases a process's allocated resources when it exits. [Microsoft process lifecycle documentation](https://learn.microsoft.com/en-us/windows/win32/procthread/terminating-a-process)

Keep Windows-specific process ownership and foreground-window operations in `Freehand.Platform.Windows`, behind interfaces. Keep orchestration, timeout decisions, retries, and recovery in the other projects.

## 4. Recording, loading, and idle memory

### Normal dictation

1. The user focuses a text field and holds Right Ctrl.
2. The app starts microphone capture without waiting for Parakeet. It records the foreground target and gives visible recording feedback without taking focus.
3. If the model is unloaded, the app starts the worker and requests model loading concurrently with capture.
4. Releasing the key stops capture. The app waits for the capture task to finish and finalizes an owned audio buffer before sending it to the worker.
5. If loading is still in progress, the app keeps the recording and shows that it is preparing the transcript.
6. The worker transcribes the recording. The app applies dictionary corrections and attempts text insertion when enabled.
7. The app retains the completed text for copying when automatic insertion is disabled or cannot finish. Persistent history follows the history setting.
8. The model stays loaded for subsequent dictations until the idle timeout expires.

Preserve Right Ctrl as the default and observe it without swallowing the key. Ignore key-repeat events. A quick press and release, release during loading, or release during capture startup must leave the engine in a valid state. Never block the keyboard hook or UI thread with native work.

Audio crossing the transcription boundary remains owned, 16 kHz mono float32 data. Preserve silence-aware segmentation with pieces no longer than the existing 60-second limit. Do not send a full long recording to the native encoder.

Bound recording memory with an initial ten-minute recording limit. At that limit, stop capture, tell the user why it stopped, and process the audio already captured. Do not silently truncate or drop it.

Support one active dictation at a time in this release. If the user presses the hotkey while a transcript is finishing or recovering, show brief busy feedback. Do not silently accept a recording that the app cannot process, and do not create concurrent recognizers.

### Idle policy

| Situation | Required behavior |
|---|---|
| App opens or starts at login. | Arm the hotkey and verify installed assets without loading the model. |
| First dictation after launch or unloading. | Load while recording; preserve the audio while waiting. |
| Another dictation within five minutes. | Reuse the loaded worker. |
| Five minutes pass after all accepted work finishes. | Gracefully stop the worker and release model memory. |
| Hotkey press races with an idle shutdown. | Resolve the transition under one lifecycle coordinator and preserve the new recording. |
| Recording, inference, recovery, or an accepted request is active. | Prevent idle shutdown. |
| Worker fails while idle. | Return to an unloaded state; start it on the next dictation. |

Use a monotonic clock for durations and the idle timer. Reset the timer after work completes. Cancel stale shutdown tasks so an old timer cannot terminate a replacement worker.

Waiting for the user to retry a failed dictation is not active worker work. Allow idle shutdown in that state while keeping the recoverable recording in the main process.

The initial idle timeout is five minutes. Expose a simple setting to change it, with five minutes as the default. Saving the setting should take effect without restarting. Release large audio buffers after successful work or explicit discard. Suspend unnecessary meter animation and interface polling while the app is hidden and idle.

A short dictation after unloading can still have a cold-start delay. Loading during speech reduces that delay but cannot guarantee it disappears. Do not keep the model loaded in the background to hide a failed performance target.

## 5. Consistency and recovery

Give model lifecycle and dictation lifecycle separate states so the app can be recording while the model loads. Use typed outcomes for capture failure, model failure, timeout, empty speech, cancellation, and delivery failure. Observe all background tasks and bring the engine back to a usable state after each outcome.

| Failure | Required response |
|---|---|
| Worker exits, pipe disconnects, or inference times out. | Keep the recording in the main process, restart the worker, and retry transcription once. |
| The automatic retry fails. | Show Retry and Discard actions. Retain the audio for the current failed dictation until the user resolves it or quits. |
| Required model assets are missing or corrupt. | Restore the verified bundled model or offer repair through the installer. Explain the failure without asking the user to start Parakeet. |
| Microphone is unavailable, disconnected, or access is blocked. | Stop capture safely, show the relevant device or Windows access action, and allow another attempt without restarting the app. |
| Microphone changes or Windows resumes from sleep. | Refresh capture and hotkey readiness. Recover stale worker connections before using them. |
| The hotkey hook cannot start. | Show a startup error and a Retry action. Do not display a working dictation state. |
| Capture produces no samples or no usable speech. | Insert nothing and show brief feedback. Do not report successful transcription. |
| The foreground target changes or text delivery fails. | Preserve the text and offer Copy. Do not automatically retry insertion. |
| History cannot be saved. | Continue delivery when possible and report the storage problem separately. |

Initial internal timeout defaults are 30 seconds for worker startup and model loading, 60 seconds per inference segment, and five seconds for graceful worker shutdown. Make them named configuration values so measurements can guide tuning. Do not loop indefinitely, repeatedly reload a broken model, or trigger repeated recovery notifications.

Keep failed audio in memory by default and retain only the current unresolved failed dictation. Resolve that failure before accepting another recording, which prevents an unbounded recovery queue. The user can retry, discard, or copy any text already produced. Persistent transcript history must not silently become an audio archive.

Identify every dictation with a stable job ID. Ignore replies from obsolete workers and requests. Transcription retry must not duplicate history or text insertion. Once text insertion starts, never replay it automatically, because a failed insertion can have delivered some characters already.

Closing the window continues background operation. Explicit Quit cancels work safely and prevents later insertion. If work would be discarded, make that consequence clear before quitting. Shutdown releases the microphone, hook, worker, pipe, timers, and process handles without waiting synchronously on the UI thread.

## 6. Text delivery, settings, and interface

Keep `SendInput` as the insertion mechanism. Preserve Unicode, punctuation, literal dictionary replacements, and whole-word correction behavior. Do not substitute UI Automation for insertion.

Record the foreground target when dictation begins and check it before insertion. If it changes, preserve the transcript for Copy instead of forcing focus or typing into another app. Check for focus changes during multi-block insertion and stop safely if needed. Report a partial or uncertain delivery without claiming the full transcript reached the target.

Apply these settings without restarting:

- Push-to-talk key, with rollback if the replacement hook cannot start.
- Automatic text insertion.
- Transcript history.
- Idle model timeout.
- Start at Windows login.

Defer changes that affect an active recording until that dictation finishes. Preserve existing settings, dictionary entries, and transcript history under `%LOCALAPPDATA%\Freehand`. Write settings atomically, and do not silently overwrite an unreadable existing file without preserving it.

Load history in bounded pages and avoid retaining an unlimited transcript collection in the interface. Long-term history must not defeat the idle memory budget.

Keep explicit dictionary corrections unchanged. Bare dictionary terms do not currently bias the Windows recognizer, so the interface must not promise that they improve recognition.

The recorder interface and tray should reflect the actual state. Provide a small nonactivating status indicator when the main window is hidden, so the user can tell whether the app is recording, preparing, finishing, or recovering. The indicator must not take focus from the target application.

Distinguish an installed model from a loaded model in settings. Show the actual resolved path, including a custom path if one is configured. Normal unloaded operation should appear ready for use, not broken. A custom path that fails should have a one-click option to return to the bundled model.

Keep the existing design tokens, flat recorder panels, bevels, and grain. Red means recording. Amber and green indicate instrumentation. Keep developer details, worker controls, and model configuration out of the normal dictation flow.

## 7. Installation and background operation

Deliver one per-user Windows x64 installer containing the self-contained application, platform assembly, required managed and native dependencies, model files, and third-party notices. The installed app must work offline and must not require an installed .NET runtime, Python, Node, CUDA, Hugging Face CLI, an account, or a manually started service.

The installer must include these pinned model assets:

- `encoder.int8.onnx`
- `decoder.int8.onnx`
- `joiner.int8.onnx`
- `tokens.txt`

Keep model assets as installed files rather than extracting them on every launch. Build a manifest with the exact model version, configuration, file sizes, and SHA-256 hashes. Validate assets during installation or repair and after detected changes. Routine hotkey presses must not rehash the entire model.

The default installation must be independent of the old checkout, its publish directories, and Sam's existing model folder. Existing verified identical assets may be reused, but a fresh installation must include everything it needs. If a configured external model becomes unavailable, the bundled model remains available through the app.

Create a Start Menu shortcut with a stable application identity and icon. Support Windows taskbar pinning and reopening the existing instance from the pinned shortcut. Start at login by default, with an in-app toggle to disable it. Login startup runs in the tray without opening the main window or loading Parakeet.

Closing the main window hides it. Tray Show, Settings, and Quit must continue working across repeated hide and reopen cycles. Keep hotkey ownership in the application lifecycle rather than a window constructor.

Upgrade must stop the old app and worker, replace the installation coherently, and preserve user data. Uninstall must remove installed binaries and login startup entries while preserving user data by default. Include model attribution and applicable dependency notices. The distributed model identifies its license as CC-BY-4.0. [Model repository](https://huggingface.co/nvidia/parakeet-tdt_ctc-110m)

One application does not require every dependency and model byte to be embedded in one executable. The installer owns those files, and the user runs one app.

## 8. Performance and diagnostics

Measure the installed Release build on Sam's computer. The existing guide's roughly 2 GB memory figure and transcription speed estimates are context, not measurements established for this machine.

Record launch-to-hotkey-ready time, press-to-first-audio time, worker startup and load time, key-release-to-transcript time, key-release-to-first-insertion time, full insertion time, and recovery time. Use monotonic durations. Include model loading and delivery in end-to-end measurements.

Use combined private bytes and working set across the main app and its worker. Report both; neither a worker-only measurement nor a drop in visible working set alone establishes the desired idle memory behavior.

These are initial engineering targets for the installed x64 build, not existing guarantees:

| Metric | Target |
|---|---|
| Unloaded idle memory with the main window hidden. | At most 250 MiB combined private bytes and no speech worker. |
| Idle CPU over a one-minute sample. | At most 1% of total machine CPU on average. |
| Model memory after the idle timeout. | Worker exits within five seconds; main-process private bytes return within 50 MiB of the comparable pre-dictation baseline after buffers are released. |
| Warm dictation with a ten-second speech clip. | P95 key-release-to-first-insertion of at most one second over at least 20 runs. |
| Cold model startup and loading. | P95 of at most three seconds over at least 20 worker starts, measured separately from capture. |
| Consistency. | 50 sequential dictations and ten unload/reload cycles without a stuck state, duplicate insertion, or orphan worker. |

Use a fixed recorded speech fixture for repeatable loading and inference measurements, and actual foreground insertion for delivery measurements. Report the hardware, clip, transcript length, run count, and failures with the results. Distinguish worker-cold starts with cached files from first use after a reboot.

If a target is missed, investigate and report the measured result. Do not silently change the target or replace the idle policy with permanent model residency. The final result should state which targets passed and which remain limited by the machine or implementation.

Keep bounded local diagnostic logs with job IDs, state transitions, timings, failure types, app version, and model version. Exclude raw audio and transcript text from diagnostic logs. Provide an in-app way to open the log folder. A settings or history storage error must not cause an unobserved exception in the dictation path.

## 9. Implementation work

Complete these workstreams as one delivery. Internal build and validation fixes are part of the implementation; Sam does not need to test intermediate versions.

| Workstream | Main areas |
|---|---|
| Worker lifecycle and protocol. | `Program.cs`, `Freehand.Speech`, abstractions, worker client, Windows process ownership. |
| Capture and dictation coordination. | `DictationEngine`, capture task ownership, explicit outcomes, idle timer, retry, cancellation. |
| Model discovery and verification. | Shared model resolver, bundled asset manifest, custom path handling, installed versus loaded status. |
| Text delivery and settings. | `SendInputTextInjector`, foreground target checks, settings subscriptions, history outcome handling. |
| Application lifecycle and feedback. | `App.axaml.cs`, composition, main window, tray, nonactivating indicator, single-instance activation, login startup. |
| Packaging. | Reproducible publish and installer scripts, full dependency inclusion, model inclusion, notices, install/upgrade/uninstall behavior. |
| Verification and documentation. | Existing tests, focused lifecycle regression coverage, published self-tests, benchmark report, installer smoke checks, final user instructions. |

Preserve the pinned package versions and sherpa-onnx's bundled ONNX Runtime. Preserve the reflected platform assembly resolver, MSBuild copy and publish targets, and explicit app-level NAudio reference. Other projects remain `net10.0`; the Windows platform project remains `net10.0-windows`. Dispatch background transcript and state updates onto Avalonia's UI thread.

Keep the shared dictionary vectors authoritative. This release does not change correction semantics. If an implementation requires such a change, update the vectors first and validate normalization, invariant matching, literal replacement, boundaries, and longest-trigger-first ordering.

## 10. Definition of done

Before handing the packaged app to Sam, the implementation must meet these requirements:

1. `dotnet build Freehand.sln -c Release --no-incremental -warnaserror` passes, and the existing tests pass after the behavior changes.
2. Focused regression checks cover loading during capture, early release, capture drain, idle shutdown races, retry limits, stale worker replies, settings application, and safe shutdown. Use fakes for lifecycle transitions and real worker integration for process and native loading behavior.
3. The actual published executable passes `--selftest` from the installer layout. Extend packaging validation to load the bundled model, transcribe a known speech fixture through the worker, shut the worker down, and start it again. File existence alone is insufficient.
4. A fresh installation starts offline without developer tools, old model folders, or the source checkout. Verify this in an isolated Windows user or equivalent clean environment.
5. Single-instance launch, login startup, hide/reopen, tray settings, explicit Quit, upgrade, and uninstall behave as specified.
6. Injected worker failure and timeout checks preserve audio, perform one automatic retry, avoid duplicate delivery, and leave no orphan process. Missing or damaged model assets produce a repair path.
7. Memory, latency, and consistency results accompany the build. Record any unmet target or environment limitation plainly.
8. Final documentation describes installation, the hotkey, background operation, the idle policy, and recovery in user terms. Remove instructions that require the user to run a separate model service or download assets manually for the packaged release.

Do not claim microphone, physical hotkey, foreground insertion, or sleep/resume behavior passed based only on fakes, headless checks, or a startup self-test. Complete what can be verified autonomously, then identify the remaining hardware checks for Sam's single final session.

## 11. Sam's final test and delivery files

Provide the installer, version and build identifier, package checksum, implementation notes, verification results, and a short test checklist. Put generated release artifacts under `artifacts/` and the written verification report under `docs/`.

Sam's final session should cover:

- Install and open the app through the normal Windows shortcut, then pin and reopen it from the taskbar.
- Dictate with the actual microphone and Right Ctrl into Notepad, a browser text field, and the usual daily application. Confirm first and last words, punctuation, corrections, and Unicode text.
- Repeat several short dictations and confirm the model stays warm and the interface stays responsive.
- Close and reopen the window, then dictate while it is hidden.
- Wait for idle unloading, confirm memory drops, and dictate again without starting anything manually.
- Change the hotkey, insertion setting, and history setting, then verify they take effect.
- Disconnect and reconnect the microphone, and try dictation after Windows sleep/resume.
- Quit and confirm all app-owned processes exit. Relaunch and verify login startup and saved settings.

The handoff is complete when there is one runnable packaged application, the agent's checks and measured results are recorded, and Sam can perform this final session without assembling dependencies or operating another service.
