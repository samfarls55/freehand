# Freehand

[![Windows build](https://github.com/samfarls55/freehand/actions/workflows/windows.yml/badge.svg)](https://github.com/samfarls55/freehand/actions/workflows/windows.yml)

Freehand is a local dictation app for Windows. Hold Right Ctrl, speak, and release. It transcribes your recording on your computer, applies your dictionary corrections, and types the result at the caret in the app where you started.

The installer includes the speech model and runtime. You don't need an account, API key, GPU, or separate speech service. Once installed, dictation works offline.

[Download for Windows x64](https://github.com/samfarls55/freehand/releases/latest) · [Report a problem](https://github.com/samfarls55/freehand/issues) · [Build from source](#build-from-source)

## What it does

- Dictates into a focused text field with a global push-to-talk key.
- Runs NVIDIA Parakeet TDT 110M locally through sherpa-onnx, using CPU inference.
- Applies explicit corrections for names, product names, and phrases.
- Keeps a searchable transcript history, with copy and delete controls.
- Runs in the Windows tray and can start when you sign in.
- Releases the speech model after five idle minutes by default.
- Retains a failed recording in memory for Retry or Discard after one automatic transcription retry.

This release supports English dictation and ships as a Windows x64 package. ARM64, macOS, and Linux packages are not provided. Text appears after you release the key.

## Install

### Requirements

- Windows 11 on a 64-bit Intel or AMD PC. Windows 10 and Windows on ARM have not been validated for this release.
- A working microphone, selected as your Windows default input device.
- About 2 GB of free disk space for the download, installed files, repair cache, and temporary setup files. The installer includes the speech model.
- Enough available memory for the speech worker. The smaller model retained about 191 MiB in isolated tests on the development machine. The desktop interface and temporary inference buffers use additional RAM. Usage and transcription time depend on your computer.

The installer includes .NET and the native speech dependencies. You don't need to install .NET or developer tools to use Freehand.

### 1. Download the installer

Open the [latest release](https://github.com/samfarls55/freehand/releases/latest). Under **Assets**, download:

- `Freehand-1.0.0-win-x64-Setup.exe`
- `Freehand-1.0.0-win-x64-Setup.exe.sha256`

The **Source code** ZIP and tarball contain source, not an installable app. Use the `Setup.exe` asset for installation.

### 2. Verify the download

Put both files in the same folder. Open PowerShell in that folder and run:

```powershell
$installer = '.\Freehand-1.0.0-win-x64-Setup.exe'
$expected = ((Get-Content -LiteralPath ($installer + '.sha256') -Raw).Trim() -split '\s+')[0]
$actual = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
if ($actual -ine $expected) { throw 'Checksum mismatch. Download the installer again.' }
'Checksum verified.'
```

### 3. Run setup

Double-click `Freehand-1.0.0-win-x64-Setup.exe` and confirm **Install or repair**. Setup verifies the package and model, installs the app, and checks that the speech worker can transcribe known speech. Leave it running until it reports that Freehand is installed.

The installer is unsigned. Windows may show an unknown-publisher or SmartScreen prompt. Check that you downloaded it from this repository and verified the checksum before proceeding. On a managed computer, follow your organization's installation policy.

Freehand installs for your current Windows user at:

```text
%LOCALAPPDATA%\Programs\Freehand
```

The default installation does not require administrator privileges. Setup adds a Start Menu shortcut and an uninstall entry. New installations start Freehand in the tray when you sign in. You can turn this off in Settings.

### 4. Enable microphone access

Open **Windows Settings > Privacy & security > Microphone**. Enable **Microphone access** and **Let desktop apps access your microphone**.

Open **Settings > System > Sound > Input**, select the microphone you want to use, and check its input level. Freehand captures the Windows default microphone.

### 5. Try your first dictation

1. Open **Freehand** from the Start Menu. You can pin that shortcut to the taskbar.
2. Open Notepad and click in its text area.
3. Hold **Right Ctrl**, speak a short sentence, then release the key.
4. Keep the text field focused while Freehand finishes processing. The transcript should appear at the caret.

The first recording loads the model while you speak, so it can take longer to finish. If you release the key before loading finishes, Freehand keeps the captured audio and processes it once the model is ready.

## Everyday use

Closing the main window keeps Freehand running. Right-click its tray icon for **Show**, **Settings**, or **Quit**. Opening Freehand again shows the existing app.

In Settings, you can change the dictation key, automatic text insertion, transcript history, login startup, and model idle timeout. Changes apply without restarting. An active dictation finishes with the settings it started with.

Right Ctrl passes through to the foreground app. Freehand observes the key without swallowing it, so avoid combining it with another shortcut while dictating. Right Alt is also available, but it acts as AltGr on many keyboard layouts.

After five minutes without accepted dictation work, the speech worker exits and frees the model's memory. The tray app and hotkey remain ready. The next recording loads the model again. Each recording stops at ten minutes and transcribes the captured audio.

If you change focus during processing or delivery, Freehand keeps the transcript for **Copy**. It doesn't move focus back. If only part of the text arrived, check the target before pasting because Freehand does not automatically repeat delivery. The latest transcript remains available when history is disabled.

### Dictionary corrections

Use the Dictionary view to add an explicit correction, such as:

```text
cloud code -> Claude Code
free hand -> Freehand
```

Corrections run after transcription. Matching ignores case and respects whole-word boundaries. Longer triggers take priority, and replacements are literal text.

You can also edit `%LOCALAPPDATA%\Freehand\dictionary.txt`. It accepts one entry per line:

```text
# A comment
cloud code -> Claude Code
# off: free hand -> Freehand
Anthropic
```

`# off:` disables a correction without deleting it. A bare term such as `Anthropic` is stored for reference; it does not bias the Windows speech recognizer. Use a `misheard phrase -> replacement` rule to change the output.

### Local data and privacy

Freehand processes audio locally. It does not upload recordings or transcripts to a speech service. Recording buffers stay in memory, including a failed recording awaiting Retry or Discard. Quitting discards unresolved audio after confirmation.

The default data folder is `%LOCALAPPDATA%\Freehand`:

| File or folder | Contents |
|---|---|
| `settings.json` | Preferences |
| `dictionary.txt` | Your terms and correction rules |
| `transcripts.jsonl` | Saved transcript history when enabled |
| `logs/` | Diagnostic states, timing, job IDs, and failure types |
| `verification/` | Model verification cache |
| `installer/` | Saved installer for repair |

History is enabled by default. Turn it off in Settings to stop saving new transcripts. Use **Delete all** in the Transcriptions view to remove existing history. Logs do not contain audio or transcript text. Local history files are plain text, so handle them like other personal documents.

### Update, repair, and uninstall

Download the installer from a newer release and run it to update. Resolve any active recording first because setup closes Freehand before replacing files. Your settings, dictionary, and history are preserved. Updates are manual.

For missing or damaged files, use **Repair bundled model** in Settings or run the installer again. If a custom model directory is unavailable, choose **Use bundled model**.

To uninstall, open **Windows Settings > Apps > Installed apps > Freehand > Uninstall**. Uninstall removes the application, shortcut, login entry, and saved repair installer. It preserves your settings, dictionary, and history. To remove those too, back up anything you need and delete `%LOCALAPPDATA%\Freehand` after uninstalling.

## Troubleshooting

| Problem | What to check |
|---|---|
| Nothing happens when you hold the key | Confirm Freehand is running in the tray and check the selected key in Settings. |
| No audio or an empty transcript | Check the Windows default input device, microphone access for desktop apps, and the input level. |
| The model says installed but unloaded | This is normal before the first dictation or after the idle timeout. Start a recording to load it. |
| The first transcript takes longer | Model loading happens on demand. Keep the text field focused until processing completes. |
| Missing or damaged model | Run setup again or use **Repair bundled model**. A custom directory must contain the exact pinned assets. |
| Processing fails twice | Fix the reported problem, then use **Retry**, or choose **Discard** before recording again. |
| Text was transcribed but not inserted | Keep the original field focused and enable automatic insertion in Settings. Use **Copy** if the app does not accept simulated text input. |
| An administrator window receives no text | Windows can block input from a normally launched app into an elevated window. Use **Copy** and paste manually. |
| Text insertion stopped partway through | Check what arrived before pasting. Freehand does not repeat an uncertain delivery. |
| You cannot find Freehand after closing its window | Check the tray, including hidden icons, or open the Start Menu shortcut again. |

Open **Settings > Open diagnostic logs** for more detail. For setup failures, also check `%TEMP%\Freehand-setup-error.log` if it exists. When [reporting an issue](https://github.com/samfarls55/freehand/issues), include the app version, Windows version, microphone type, steps to reproduce, and relevant diagnostic lines. Review logs for personal file paths before sharing them.

This is an early public release. Build, regression, packaging, and native speech checks have passed on the development machine. Physical hotkey and microphone behavior, taskbar pinning, login startup, and sleep/resume still need broader hands-on validation. See the [verification notes](docs/WINDOWS-VERIFICATION.md) for what was tested and the known latency limits.

## Build from source

For the development, local update, and public release process, read
[Development and deployments](docs/DEVELOPMENT.md). The scripts there select the SDK,
keep development data separate, and provide repeatable verification and installation.

Build the Windows app on Windows x64. Install:

- [Git for Windows](https://git-scm.com/download/win).
- [.NET 10 SDK](https://dotnet.microsoft.com/en-us/download/dotnet/10.0). `global.json` specifies `10.0.100` and allows later .NET 10 feature bands. A runtime-only installation cannot build the app.
- [PowerShell 7](https://learn.microsoft.com/en-us/powershell/scripting/install/install-powershell-on-windows). The packaging script uses PowerShell 7 APIs; Windows PowerShell 5.1 is not sufficient.

Open a new PowerShell 7 window after installing the tools. Clone the repository and check the SDK from inside it:

```powershell
git clone https://github.com/samfarls55/freehand.git
Set-Location freehand
dotnet --version
pwsh --version
```

### Build and test

```powershell
dotnet restore Freehand.sln
dotnet build Freehand.sln -c Release --no-incremental -warnaserror
dotnet test Freehand.sln -c Release --no-build
```

The build treats compiler and analyzer warnings as errors. Keep dependency versions in `Directory.Packages.props` pinned unless you are deliberately updating them.

### Create the full installer

```powershell
pwsh -File .\scripts\build-release.ps1 -Dotnet (Get-Command dotnet).Source
```

The script publishes a self-contained x64 app, downloads the pinned model and known speech fixture, verifies their SHA-256 hashes, collects dependency notices, and embeds the complete package in the installer. An internet connection is needed for NuGet restore and uncached downloads. The model files total about 130 MiB.

The script can reuse matching model files from your installed app or its build cache. To use an existing download in another folder:

```powershell
pwsh -File .\scripts\build-release.ps1 -Dotnet (Get-Command dotnet).Source -ModelSource 'C:\models\parakeet-110m'
```

That directory must contain the files listed in [packaging/model-manifest.json](packaging/model-manifest.json). A different model revision will fail verification. The cache is only a build input. The installed app uses its own bundled files.

Build outputs are:

```text
artifacts/publish/                         Complete unpacked application
artifacts/release/Freehand-1.0.0-win-x64-Setup.exe
artifacts/release/Freehand-1.0.0-win-x64-Setup.exe.sha256
```

Run the generated installer using the installation steps above. You can also launch `artifacts/publish/Freehand.App.exe` to try the unpacked app. Keep the whole publish folder together, including the platform DLL, native libraries, and `models` directory. Copying only the executable will not produce a working installation.

A plain `dotnet run --project src/Freehand.App -c Release` does not download or bundle the model. Package the app first, or place the exact model assets in the build output's `models/parakeet-110m` folder. See [model setup](docs/PARAKEET-WINDOWS.md) for the inference configuration.

### Verify the package

Run the self-test against the published executable. `Start-Process -Wait` is required to reliably collect the exit code of this Windows GUI app:

```powershell
$app = (Resolve-Path '.\artifacts\publish\Freehand.App.exe').Path
$check = Start-Process -FilePath $app -ArgumentList '--selftest' -Wait -PassThru -WindowStyle Hidden
if ($check.ExitCode -ne 0) { throw "Self-test failed with exit code $($check.ExitCode)." }
```

With the full package present, this checks dictionary and storage behavior, reflected Windows platform loading, native model loading, known speech transcription, and worker stop/restart. It does not verify physical microphone capture or hotkey delivery into another app. The installer also runs this check against the installed executable.

The [Windows workflow](.github/workflows/windows.yml) builds, tests, packages, and runs the published self-test. Its downloadable artifact contains the installer and checksum.
Pushing a version tag also publishes a GitHub Release after those checks pass. See
[the release process](docs/DEVELOPMENT.md#publish-a-version) for versioning and release notes.

## Contributing

Start with an [issue](https://github.com/samfarls55/freehand/issues) for a bug or a proposed change. Include a concrete reproduction or describe the behavior you want. For code changes, run the build and tests above and explain how you verified the affected behavior.

| Path | Responsibility |
|---|---|
| `src/Freehand.App` | Avalonia interface, tray, startup, and composition |
| `src/Freehand.Core` | Dictation coordination, settings, dictionary storage, and paged history |
| `src/Freehand.Speech` | Model verification, speech worker, protocol, and Parakeet inference |
| `src/Freehand.Dictionary` | Literal dictionary corrections |
| `src/Freehand.Abstractions` | Capture, hotkey, delivery, lifecycle, and process interfaces |
| `src/Freehand.Platform.Windows` | WASAPI, keyboard hook, SendInput, and Windows process ownership |
| `packaging` | Installer, pinned model manifest, and third-party notices |
| `tests` | Dictionary contract, lifecycle, storage, protocol, and headless UI tests |

Keep Windows APIs in `Freehand.Platform.Windows`. The app loads that assembly by reflection, so preserve its copy and publish targets and the app's explicit NAudio reference. Any packaging change needs a self-test against the published executable.

[shared/dictionary-test-vectors.json](shared/dictionary-test-vectors.json) defines the dictionary behavior contract. Change the vectors first when changing correction semantics, then update the implementation and run the dictionary tests. Build outputs, models, personal recordings, history, secrets, and local work records belong outside Git.

Read [AGENTS.md](AGENTS.md) for project constraints and [the implementation notes](docs/WINDOWS-IMPLEMENTATION.md) for lifecycle and recovery details.

## Attribution and license status

Freehand derives from the Windows implementation in [Pat Simmons's Murmur repository](https://github.com/per-simmons/murmur-youtube). That source was adapted into this standalone Windows application. The [source record](docs/ORIGIN.md) documents its origin, migration, and rename, and the original copyright attribution is retained.

This repository is public, but it does not grant a new software license. The upstream repository had no license file when this release was prepared. Public availability does not establish an open-source license or grant general reuse rights. Resolve the applicable permissions before redistributing or adapting the application code.

The speech model and dependencies have their own licenses. The pinned Parakeet distribution identifies its model license as CC-BY-4.0, and sherpa-onnx uses Apache-2.0. Attribution and dependency notices are included in [packaging/THIRD-PARTY-NOTICES.txt](packaging/THIRD-PARTY-NOTICES.txt) and each installed package's `licenses` folder. Those licenses do not license the Freehand application code.
