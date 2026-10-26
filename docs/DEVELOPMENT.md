# Development and deployments

Use the development build while changing Freehand. Update the installed app after
the change works. Merging application changes to `main` publishes a verified release
that installed copies can discover.

| Command | Result |
|---|---|
| `pwsh -File ./scripts/setup-dev.ps1` | Finds a compatible SDK or installs the pinned SDK locally, then restores dependencies |
| `pwsh -File ./scripts/dev.ps1` | Builds and opens the development app with a separate data folder |
| `pwsh -File ./scripts/verify.ps1` | Runs the Release build with warnings as errors and the .NET regression tests |
| `pwsh -File ./scripts/verify.ps1 -Package` | Also creates the installer and tests the published executable |
| `pwsh -File ./scripts/deploy-local.ps1` | Verifies and packages the changes, saves the previous repair installer, then updates the installed app |

Run commands from the repository root in PowerShell 7 on Windows x64. Each build
command accepts `-Dotnet 'C:/path/to/dotnet.exe'` when the SDK is elsewhere.

## First setup

Run `setup-dev.ps1` once. The local SDK lives in `.dotnet`, which Git ignores.
The scripts select it automatically without changing your permanent PATH or the
SDK configuration in `global.json`. This uses Microsoft's
[SDK installation script](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-install-script).
You can also install the SDK normally and let the scripts find it.

Development reuses the pinned model from an existing installation or build cache.
On a new machine, run `verify.ps1 -Package` once to download and verify the model.
Use `-ModelSource 'C:/models/parakeet-110m'` to select an existing download. Packaging
keeps a verified cache under `artifacts/model-cache` so later builds can reuse it.
The model download is a pinned upstream `.tar.bz2` archive. Packaging verifies the
archive before extraction with Windows `tar`, then verifies each model file separately.

## Make a change

1. Start from current `main` and create a branch named `codex/<change>`.
2. Make the change. Update dictionary vectors first if correction semantics change.
3. Quit the installed app from its tray menu, then run `dev.ps1`. Only one copy can
   own the global dictation key. Re-run the command after quitting the development
   app to compile the next set of changes.
4. Run `verify.ps1`. Run `verify.ps1 -Package` for changes to startup, speech, native
   dependencies, publishing, or installation. Fix failures before proceeding.
5. Try the affected behavior in the development app. Changes involving capture,
   hotkeys, or text insertion need a physical microphone, a physical key press, and
   a foreground text field. Automated checks do not establish those hardware claims.
6. Commit the verified source. Push the branch when you want it on GitHub. Open a
   pull request ready for review when requested, then merge after its checks pass.

The development profile lives in `artifacts/dev-data`. Its settings, dictionary,
history, verification cache, and logs are separate from your installed app's data.
It does not change Windows login startup. The first development launch uses a fresh
dictionary; add test rules there as needed. `dev.ps1 -BuildOnly` builds and prepares
the profile without opening a window.

The SonarQube job runs the .NET tests under the pinned `dotnet-coverage` tool and
the deployment-script tests under Pester 6.2.0. It imports both reports into the
existing quality gate. Run the script tests locally with
`pwsh -File ./tests/Freehand.Scripts.Tests/Run.ps1` using PowerShell 7.4 or later.
The runner downloads the exact Pester package directly and verifies its pinned
SHA256 before extraction. It reuses the local test-tool cache on later runs.
They execute unchanged copies of the scripts in a temporary fixture, with simulated
SDK and installer processes. Your installed app and normal profile stay outside that
fixture. Windows regression tests also check that an isolated profile leaves the
installed app's login entry unchanged.

SonarQube also collects coverage from the public-fixture performance replay through the
real speech worker. A separate unbundled publish exposes the managed assemblies to the
profiler. The Windows job verifies the shipped single-file package. Replay measurements
made under the profiler include instrumentation overhead and are correctness checks,
not comparable latency or memory benchmarks.

## Update this computer

Quit the development app and resolve any active or retained recording in the installed
app. Run:

```powershell
pwsh -File ./scripts/deploy-local.ps1
```

The command stops on a failed build, test, published self-test, or checksum check.
It saves the previous repair installer under `artifacts/rollback`, then runs the new
installer. Setup closes the installed app, replaces its complete package, and tests
the installed executable. The updated app starts in the tray after setup succeeds.
Your normal settings, dictionary, and history stay in `%LOCALAPPDATA%/Freehand`.

Local deployment can include uncommitted changes. The package records the source
commit and adds `-dirty` when the workspace contains uncommitted changes. The installed
`package-manifest.json` and diagnostic startup log identify the build you are running.
Prefer deploying committed source when recording a final verification result.

To install an already built package, or restore a saved version:

```powershell
pwsh -File ./scripts/deploy-local.ps1 -InstallerPath 'C:/path/to/FreehandSetup.exe'
```

Keep its `.sha256` file alongside it. The script prints the rollback path whenever
it saves a previous installer. Restoring an installer changes application files;
it does not restore older user data. Future changes to stored data must keep older
versions compatible or include a documented data backup and recovery step.

Add `-WhatIf` to preview the installation target. With `-InstallerPath`, this checks
the checksum without changing the installation. Without it, the command builds and
verifies the package before previewing the installation.

## Publish a version

Merging to `main` is the decision to ship. The Windows workflow automatically:

1. Selects the next patch version from existing release tags and the baseline in
   `Version.props`. All main runs queue together, including the publication job.
2. Builds and tests the source, creates the installer, and runs the published self-test.
3. Verifies an isolated package upgrade, corrupt-payload rejection, and rollback after
   an installed self-test failure. Runs the deployment and release script tests.
4. Reserves the version tag, uploads the tested installer and checksum to a draft release, generates release
   notes from GitHub PRs, verifies both uploaded assets, then publishes the release.

The workflow passes `FREEHAND_RELEASE_VERSION` to MSBuild and the packaging scripts,
so the executable, installer, manifest, asset names, and Windows uninstall entry agree.
It does not commit version changes back to the repository. To start a new minor or
major version, raise the baseline in `Version.props`. Local builds use that baseline
unless an explicit `FREEHAND_RELEASE_VERSION` is set.

PRs run verification without publishing. Documentation-only merges skip the Windows
workflow. A failed check leaves the last published release available. An outdated main
build skips publication if a newer application commit has arrived. Documentation-only
commits do not suppress an otherwise verified release. Rerunning the current
commit reuses its tag and leaves already published assets unchanged. An incomplete
draft can be retried. Its reserved tag keeps later changes from reusing that version.
Keep published tags and assets unchanged.

Use **Run workflow** on `main` to retry a failed release. Running the workflow on a
different branch verifies that branch without publishing it. Publication happens in
the same workflow using its repository token, so no personal token or second tag-triggered
workflow is needed. The token needs Contents write permission only in the release job.

Installed copies check shortly after startup and every six hours. Settings includes a
manual check and a switch for automatic checks. A check requests public GitHub release
metadata without credentials, audio, transcript text, or settings. Downloads begin only
after **Update** is accepted. Setup waits for idle dictation and restarts the app after
success or restoration of the previous version. Development and isolated profiles do
not check for updates or launch the installed updater.

The first updater-enabled build requires a manual installation because older copies
cannot discover releases. Use `deploy-local.ps1` to bootstrap this computer. After the
workflow is merged, installed copies will offer newer published versions.

For packaging changes, also run:

```powershell
pwsh -File ./scripts/verify-updates.ps1
```

Run it after `verify.ps1 -Package`. It wraps the real published payload in fixture
packages with versions `0.0.1`, `0.0.2`, and `0.0.3`. The last has a correctly hashed
but broken speech fixture, so installed verification must fail and restore `0.0.2`.
The test uses separate installation and data directories and skips Windows registration.
It starts the real app executable in a headless handoff mode with profile-scoped Windows
ownership, then verifies that `--update` stops and restarts it after success and rollback.
The probe arms no capture or hotkey and never changes the normal installation.
Failed fixtures and setup logs remain under `artifacts/update-verification` for diagnosis;
CI also uploads the setup error logs. Successful fixtures are removed.
These checks establish package replacement and recovery, not physical microphone or
hotkey behavior.

GitHub documents [draft-first publication](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)
and [workflow queuing](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

## Completion report

After a change, state which checks passed, whether the installed copy was updated,
the version and source commit deployed, and whether a GitHub Release was published.
Source completion, local installation, and public publication are separate results.
