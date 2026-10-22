# Working on Freehand for Windows

This project contains the Windows implementation of Freehand. Use Parakeet through
sherpa-onnx for speech recognition. The solution, source, and tests are at the project root.
Read [README.md](README.md) for build commands and
[docs/PARAKEET-WINDOWS.md](docs/PARAKEET-WINDOWS.md) for model setup.

For development, local installation updates, or public releases, read and follow
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). Report source changes, installed updates,
and GitHub publication separately.

## Preserve the behavior contract

`shared/dictionary-test-vectors.json` specifies dictionary correction behavior.
Change the vectors first when changing correction semantics, then update the implementation
and run the dictionary tests. Preserve NFC normalization, culture-invariant matching,
literal replacements, whole-word boundaries, and longest-trigger-first ordering.

## Keep the platform boundary

Keep capture, keyboard hooks, and text injection in `Freehand.Platform.Windows`.
Keep orchestration, retries, and device recovery behind interfaces in the other projects.
The platform project targets `net10.0-windows`; the other projects target `net10.0`.

`Freehand.App` loads the platform assembly by reflection. Preserve its MSBuild copy and
publish targets, the assembly resolver, and the explicit NAudio package reference in the
app. A startup self-test must exercise the published executable after packaging changes.

## Preserve the Windows configuration

- Right Ctrl is the default push-to-talk key. Observe the key without swallowing it.
- Audio reaching the transcriber is owned, 16 kHz mono float32 data.
- Use `SendInput` for text insertion at the caret. UI Automation is not a substitute.
- Keep native model loading and inference off the keyboard hook thread.
- Dispatch background transcript updates onto Avalonia's UI thread.
- Parakeet TDT 110M uses CPU inference, four threads, 80 features, and `nemo_transducer`.
  `packaging/model-manifest.json` pins its assets and configuration.
- Preserve the versions in `Directory.Packages.props` unless updating dependencies is
  part of the requested work. sherpa-onnx provides its own ONNX Runtime.

## Keep the Compact design

Use the tokens in `src/Freehand.App/Design/DesignTokens.cs` for interface styling.
Follow [DESIGN.md](DESIGN.md) for the approved Compact interface: a dark graphite window,
text tabs, readable transcript rows, and restrained sage actions. Red indicates recording;
amber indicates attention. Keep dictation in the tray and preserve native Windows controls.

## Verify the affected behavior

Use `dotnet build Freehand.sln -c Release --no-incremental -warnaserror` for compiler and
analyzer validation. Run the existing tests after behavior changes. Use the published
executable's `--selftest` for packaging checks. Hardware claims require an actual microphone,
physical hotkey, and delivery into a foreground text field.

## Migration baseline

The Windows source was moved into this folder on October 8, 2026. Its existing local
fixes were retained. The source origin and upstream commit are recorded in
[docs/ORIGIN.md](docs/ORIGIN.md). Earlier development history is retained locally
outside the public repository history.

The shared dictionary vectors were copied so the original checkout keeps its contract.
This project now maintains its own copy. Migration hashes and the original local changes
are saved under `work/`.
