# Local handoff: unresolved Windows text-delivery corruption

Updated November 4, 2026. Branch: `codex/scribekey-blend-dev`.
Application code immediately before this handoff: `763616af5abc85408963dc7a1a3c94f4c5906269`.

## Current status and assignment

**The issue is NOT resolved.** The user still sees corrupted text outside Freehand
after both attempted fixes below. The transcript displayed inside Freehand is
correct. Previous messages describing the issue as fixed were not supported by
the user's subsequent local results. Treat the automated tests as coverage, not
proof that this machine's failure has been reproduced or corrected.

The user requested this handoff so a local agent on the affected Windows machine
can diagnose the actual failure. Reproduce the real Right-Ctrl dictation workflow
into the user's Notepad, establish the cause, fix it, and verify the received text
on this machine. Do not resume model training or change the selected blend as part
of this delivery investigation. Training was explicitly stopped.

Read `AGENTS.md` and `docs/DEVELOPMENT.md`. Preserve existing work, installed-app
data, and earlier preview folders. Work on the development branch. Do not update
the normal installation, merge to main, or publish a normal release.

## Exact reported examples

Example 1, correct text displayed in Freehand:

```text
Testing, testing, testing, this is an interesting thing and I really want to see if it works and I really hope that it's best.
```

What the user received in Notepad:

```text
Testing,nnnnnng bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbest.
```

Example 2, correct text displayed in Freehand:

```text
Trying one more time, I know sometimes the first dictation might not always be perfect.
```

What the user received in Notepad, quoted to retain the trailing spaces:

```text
"Trying one more time, I know sometimes the first dictation might not always             "
```

Earlier description: text cuts off and then adds a line of spaces. After the
latest code, the user said they are still experiencing issues; they have not
provided a separate post-latest-fix output. The strings above remain the concrete
reproduction examples. The affected Windows/Notepad versions, input layout/IME,
other keyboard utilities, and the exact running binary have not been inspected
locally by the cloud agent.

## What was attempted

1. `9566111`: reduced Unicode input blocks from128 to32 UTF-16 units, kept4ms
   block pacing and surrogate pairs, waited up to1s for physical modifiers before
   delivery, stopped if modifiers appeared during delivery, and sent a matching
   key-up if a partial `SendInput` result ended on key-down. Normalized lone
   CR as well as CRLF/LF to real Return events. These did not resolve the user's
   problem.
2. `0282c16`: corrected **the diagnostic test field**, not Notepad. The owned
   Windows EDIT control in `WindowsDeliveryProbe` lacked `ES_AUTOVSCROLL`, so it
   rejected long text once the visible field filled. Added vertical scrolling and
   autoscroll. This was a test-fixture defect, not evidence about the user's
   Notepad window style.
3. `37a5b54` / `8f32610`: replaced multi-character Unicode packet bursts with
   target-layout scan-code key pairs for printable ASCII that needs no modifiers.
   Uses target thread HKL, `VkKeyScanEx`, `MapVirtualKeyEx`, and `ToUnicodeEx` flag4
   to check the translation without changing the dead-key buffer. Uppercase,
   modifier-requiring keys, Caps Lock, unsupported layouts/characters and
   non-ASCII fall back to one Unicode scalar per call, paced1ms. Scan-code blocks
   remain32 characters/4ms. No synthesized Shift/AltGr chords or clipboard changes.
4. `763616a`: adjusted an old test's pause counter to distinguish modifier waiting
   from the new per-scalar pacing; retained its no-typing-with-modifier and exact
   text assertions. Added upload of regression XML to the dev workflow.

**No cause has been confirmed on the affected machine.** Unicode-packet/text-
services compatibility was a hypothesis motivating attempt3, not a proven local
diagnosis. Partial-write and modifier guards address real unsafe cases, but they
do not explain the user's continuing corruption by themselves. Avoid another
timing-only change followed by a claim of resolution without local reproduction.

## Relevant implementation

- `src/Freehand.Core/DictationEngine.cs`: `ProcessAsync` delivery section. Creates
  `insertionText` from the completed cleaned transcript, adds a single separating
  space when needed, tries to pause the hotkey, calls the targeted injector once,
  then restores listening. A failed pause currently does not prevent injection;
  the injector independently checks physical modifiers.
- `src/Freehand.Platform.Windows/SendInputTextInjector.cs`: current transport,
  layout mapping, Unicode fallback, pacing, modifier checks and short-write
  handling. `SendInput` accepting events does not prove that the recipient
  displayed the exact text. Retrying the whole transcript after uncertain input
  can duplicate already delivered text and must remain prohibited.
- `src/Freehand.Platform.Windows/PushToTalkHook.cs`: hook thread, injected-event
  tag, `TryPauseForDeliveryAsync`, pause eligibility and hook restart.
- `src/Freehand.Platform.Windows/WindowsForeground.cs`: original foreground
  HWND/process check; it does not track the focused child control.
- `src/Freehand.Platform.Windows/WindowsDeliveryProbe.cs`: diagnostic owned EDIT
  field; not the user's actual editor.
- `src/Freehand.App/Composition.cs` and `PlatformFactory.cs`: injector composition
  and reflected loading of the loose `Freehand.Platform.Windows.dll` beside the
  executable. Verify the actual loaded build before assuming the newest source
  is the code currently running.
- `tests/Freehand.Windows.Tests/TextInjectionTests.cs`: fake native-boundary
  guards, scan-code selection, Unicode scalar boundaries, exact example replay
  and real owned EDIT readback.
- `tests/Freehand.Windows.Tests/NotepadDeliveryTests.cs`: launches an owned
  `%SystemRoot%/System32/notepad.exe`, types both exact examples directly through
  the injector, reads its Edit/RichEdit child with `WM_GETTEXT`, and terminates
  only the process it launched. This bypasses capture, inference and the real
  hotkey pause/restart lifecycle. It may not match the user's Notepad version or
  input stack.

## Verify which instance is actually running

From the local repository in PowerShell7, preserve any local changes first:

```powershell
git status --short
git branch --show-current
git log -5 --oneline
Get-CimInstance Win32_Process -Filter "Name = 'Freehand.App.exe'" |
    Select-Object ProcessId, ExecutablePath, CommandLine
Get-Process -Name notepad -ErrorAction SilentlyContinue |
    Select-Object Id, Path, MainWindowTitle
```

Do not assume that the installed shortcut or an older portable launcher runs the
latest source. For a source-built preview the layout is:

```text
artifacts/scribekey-dev-<generation>/
  build-identity.json
  Start Freehand ScribeKey Dev.ps1
  Start Freehand ScribeKey Dev.cmd
  app/Freehand.App.exe
  app/Freehand.Platform.Windows.dll
  profile/settings.json
  profile/logs/freehand.log
```

Check the active executable's parent preview directory, its `build-identity.json`,
the platform DLL's hash/version, and the `app-<informational-version>` startup
entry in its log. Logs are bounded metadata; they do not contain transcript
text or a per-event keyboard trace. A newly built preview has a separate profile;
do not assume the newest directory contains the user's earlier reproduction.
Do not mistake `artifacts/scribekey-dev-cache` for a preview.

Quit the running copy from its tray menu, then fetch/build if needed:

```powershell
git config core.longpaths true
git fetch origin
git switch codex/scribekey-blend-dev
git pull --ff-only
git lfs pull
pwsh -NoProfile -File ./scripts/dev-scribekey.ps1
```

Setup builds a fresh Release preview, verifies the bundled model startup, prints
its path and launches it. PowerShell7 and the .NET10 SDK are needed; use the
existing `scripts/setup-dev.ps1` if necessary. The weights are already in Git LFS.
Use Right Ctrl for push-to-talk unless the active preview's settings say otherwise.

## Local investigation to perform

1. Reproduce into the same Notepad process the user normally uses, through the
   full physical-key workflow. Compare the complete displayed transcript and
   received text, including lengths, repeated characters and trailing whitespace.
   Record the active Freehand build, Notepad executable/version, Windows version,
   process architectures, foreground/focused-child HWND/thread, keyboard layout,
   IME/Caps Lock/modifier state and any relevant remapping/accessibility tooling.
   These are observations to collect, not causes already established.
2. Replay the exact strings without speech through the same injector into that
   same editor. Compare with the full workflow, with hook listening/paused and
   after its restart. This distinguishes receiver/transport behavior from a
   lifecycle problem. Observe which actual route is used: scan code or Unicode
   fallback; do not assume every English character maps.
3. Add temporary local diagnostics at the native boundary if needed: actual input
   struct size/offsets and flags, requested/accepted event counts, timestamps,
   thread/layout/focus and hook state. Trace what the receiving control gets if
   practical. On Windows x64 the expected INPUT size is40 bytes, its union starts
   at offset8, and KEYBDINPUT is24 bytes; check the running build rather than
   assuming its ABI. Keep real user transcripts, settings, recordings and logs local;
   the two explicitly supplied generic examples are safe test fixtures.
4. Capture a failing local case before changing more code. Preserve focus checks,
   cancellation, balanced key-up handling and no automatic replay of uncertain
   delivery. Keep Win32 behavior behind the Windows platform boundary. Preserve
   the clipboard behavior and use SendInput for caret insertion, as required by
   the repository; do not silently substitute UI Automation or clipboard paste.
5. Verify the fix repeatedly through the real user workflow in this Notepad,
   including both examples, longer text, punctuation, repeated letters, Unicode,
   successive dictations and focus changes. Run the relevant regression checks
   and published startup self-test. Report automated evidence separately from
   what was actually reproduced and fixed locally.

## Existing automated evidence and its limits

- [Latest verified Windows run](https://github.com/samfarls55/freehand/actions/runs/41876705156),
  code `763616a`: zero build warnings/errors,811/811 tests passed, zero skips;
  includes97 Windows tests and the two direct Notepad cases. Published bundled
  model startup self-test passed. The user subsequently still reported failure.
- The run retains `ScribeKey-dev-test-results` XML and the portable dev artifact.
  An earlier8f run passed the Notepad cases but failed only the outdated fake
  pause-count assertion. That assertion was corrected in763; do not confuse
  these two runs or describe the earlier failed run as fully passing.
- CI does not exercise this user's physical Right-Ctrl/capture/inference/hook
  lifecycle, their editor version, or their keyboard/text-services environment.
- For local .NET checks, use `scripts/verify.ps1`; the Windows tests can also be
  targeted with `dotnet test tests/Freehand.Windows.Tests -c Release --filter
  "FullyQualifiedName~TextInjectionTests|FullyQualifiedName~NativeTextDeliveryTests|FullyQualifiedName~NotepadDeliveryTests"`.
  The native tests create foreground windows; run them in a controlled local
  desktop session, not while entering unrelated text.

## Model and scope remain unchanged

Selected dev model: V8/V9 50/50 factor blend, original IQ4_XS base plus rank8 F32
adapter at scale1, CPU4, batch64/micro64, F16 caches, lookup16 and CompactV3.
Base SHA256: `82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174`.
Adapter SHA256: `4d14e22826d039a12444236124459363f02e77de247117b7b8379ccfe257cfb1`.
No training is authorized by this handoff. The current task is local delivery
diagnosis and repair; the cloud-only research `work/` files are not needed.
