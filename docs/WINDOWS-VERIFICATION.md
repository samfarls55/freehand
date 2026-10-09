# Windows verification

Freehand is an early Windows x64 release. Automated checks establish build, storage, dictionary, speech-worker, and packaging behavior. Physical microphone capture, the physical dictation key, and delivery into everyday foreground apps need hands-on validation.

## Build and regression checks

The Windows source passed these commands on October 9, 2026 using .NET SDK 10.0.100:

```powershell
dotnet build Freehand.sln -c Release --no-incremental -warnaserror
dotnet test Freehand.sln -c Release --no-build
```

The build reported zero warnings and errors. All 84 tests passed with none skipped, including 24 dictionary tests, 46 core tests, and 14 headless app tests.

Coverage includes capture and model-load overlap, early key release, idle shutdown races, stale replies, bounded worker timeouts, retry limits, stable job IDs, settings rollback, safe Quit, paged history, unreadable settings preservation, and model repair while failed audio is retained. Dependency versions and the shared dictionary contract remain pinned.

## Package checks

The release script produces a self-contained x64 application and a per-user installer. The package contains the runtime, reflected Windows platform assembly, native dependencies, pinned model, known speech fixture, manifests, and third-party notices. The installer validates the payload and model, then runs the installed executable's model check and self-test.

The packaged executable's `--selftest` verifies dictionary and storage behavior, reflected platform loading, native speech-model loading, known speech transcription, and worker stop/restart. Run it using the instructions in the [README](../README.md#verify-the-package).

Before publication, installation checks covered repeat installation, upgrade, model corruption detection, repair, and uninstall. Upgrade preserved settings, dictionary, and history. Uninstall removed application files and Windows registrations while preserving user data.

Earlier desktop checks covered single-instance activation, ten native hook rearm cycles, five window hide/reopen and Settings cycles, tray startup, explicit Quit, and child-worker termination after its owner exited. They did not press a physical key or capture microphone audio.

An isolation check launched the installed executable with a temporary working directory, isolated data profile, Windows-only PATH, a nonexistent DOTNET_ROOT, and the older model cache unavailable. Native speech and desktop self-tests passed using the installed model. This was not a separate Windows user or a physically disconnected network test.

Detailed local package and benchmark logs remain outside the public repository because they contain machine-specific paths. Release checksums are provided alongside the installer on [GitHub Releases](https://github.com/samfarls55/freehand/releases).

## Recorded performance and limits

These measurements came from the same Windows implementation before its rename to Freehand. The development machine ran Windows 11 with an Intel Core Ultra 7 155H, 22 logical processors, and about 16 GB of RAM. Measurements are observations on that machine, not minimum requirements or performance guarantees.

Speech inference used CPU, four threads, 128 features, and `nemo_transducer`. The fixture was the first ten seconds of the pinned JFK speech sample identified in [the third-party notices](../packaging/THIRD-PARTY-NOTICES.txt). The resulting transcript had 108 characters. P95 used nearest rank.

| Measurement | Result | Limit |
|---|---|---|
| Hidden app, model unloaded | 58.79 MiB private memory | Empty history profile |
| Idle CPU over one minute | 0.070% of total machine CPU | Normalized across 22 logical processors |
| Worker exit after five idle minutes | Five minutes plus 83.2 ms | Automated desktop measurement |
| Private memory after worker exit | 59.23 MiB | 0.44 MiB above unloaded baseline |
| Loaded app and worker | About 820 MiB private memory, 908 MiB working set | One desktop sample |
| Cold worker startup and model loading P95 | 3,574.4 ms across 20 starts | Missed the initial three-second target |
| Warm release-to-transcript P95 | 718.2 ms across 50 runs | Excludes text delivery |
| Worker-crash recovery | 4,977.4 ms with a successful transcript | Injected worker crash |
| Processing consistency | 50 transcriptions, 20 worker cycles, no failures or orphans | Final foreground delivery samples unavailable |

Cold runs started a new worker with cached model files; they do not represent first use after reboot. The benchmark supplied fixture audio through the dictation engine. It did not measure physical key press to first audio.

Foreground delivery results varied. An earlier 50-sample run matched the full transcript each time and measured 586.6 ms P95 to first insertion. A later 36-sample run measured 1,156.6 ms and missed the initial one-second target. In the final run, Windows refused activation of the benchmark's foreground field, so no final delivery latency samples were collected. Cold-load and delivery latency variation remain unresolved.

The app retains its five-minute idle policy. It does not keep the model permanently loaded to reduce those measurements.

## Hands-on verification checklist

1. Install, open the Start Menu shortcut, pin it to the taskbar, and reopen it. Confirm one app window and one tray icon.
2. Hold Right Ctrl and dictate into Notepad, a browser field, and your usual app. Check the first and last words, punctuation, dictionary corrections, and Unicode.
3. Repeat short dictations. Close and reopen the window, then dictate while it is hidden. Confirm the recording indicator leaves focus in the text field.
4. Wait five minutes after finishing. Confirm the worker exits and memory drops, then dictate again.
5. Change the key, insertion, history, and idle settings. Confirm they apply without restarting. Interrupt focus during delivery and check the retained transcript and Copy action.
6. Disconnect and reconnect the microphone, then try after Windows sleep/resume. Check recovery and a later recording.
7. Quit and confirm no app-owned process remains. Relaunch and check saved settings. Sign in again to check tray startup and its toggle.

Open diagnostic logs from Settings if a step fails. Review any personal paths before sharing log excerpts in a public issue.
