#Requires -Version 7.0
param([string]$PublishDirectory, [string]$InstallerRuntime)
. (Join-Path $PSScriptRoot 'common.ps1')
$fixture = Join-Path $projectRoot ('artifacts/update-verification/' + [guid]::NewGuid().ToString('N'))
$payload = Join-Path $fixture 'payload'
$installed = Join-Path $fixture 'installed'
$testProfile = Join-Path $fixture 'data'
$runtime = if ($InstallerRuntime) { $InstallerRuntime } else { Join-Path $projectRoot 'artifacts/installer-runtime/Freehand.Installer.exe' }
if (-not $PublishDirectory) { $PublishDirectory = Join-Path $projectRoot 'artifacts/publish' }
if (-not (Test-Path -LiteralPath $runtime)) { throw 'Run verify.ps1 -Package first.' }
New-Item -ItemType Directory -Path $payload, $testProfile -Force | Out-Null
Get-ChildItem -LiteralPath $PublishDirectory | Copy-Item -Destination $payload -Recurse
$manifestPath = Join-Path $payload 'package-manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
foreach ($name in @('settings.json', 'dictionary.txt', 'transcripts.jsonl')) {
    Set-Content -LiteralPath (Join-Path $testProfile $name) -Value ('preserved-' + $name)
}
$before = @{}
Get-ChildItem -LiteralPath $testProfile -File | ForEach-Object { $before[$_.Name] = (Get-FileHash -LiteralPath $_.FullName).Hash }

function Invoke-IsolatedSetup([string]$Path, [switch]$Update) {
    $start = [Diagnostics.ProcessStartInfo]::new($Path)
    $start.UseShellExecute = $false; $start.CreateNoWindow = $true; $start.WindowStyle = 'Hidden'
    $mode = if ($Update) { '--update' } else { '--quiet' }
    foreach ($argument in @($mode, '--isolated', '--directory', $installed)) { $start.ArgumentList.Add($argument) }
    $start.Environment['FREEHAND_DATA_DIRECTORY'] = $testProfile
    $start.Environment['FREEHAND_UPDATE_HANDOFF_TEST'] = '1'
    $process = [Diagnostics.Process]::Start($start)
    try {
        if (-not $process.WaitForExit(240000)) { $process.Kill($true); throw 'Isolated setup timed out.' }
        return $process.ExitCode
    } finally { $process.Dispose() }
}
function Wait-IsolatedHost([int]$PreviousId = 0) {
    $ready = Join-Path $testProfile 'update-handoff.pid'
    $limit = [DateTime]::UtcNow.AddSeconds(30)
    do {
        if (Test-Path -LiteralPath $ready) {
            $text = (Get-Content -LiteralPath $ready -Raw).Trim()
            $identifier = 0
            if ([int]::TryParse($text, [ref]$identifier) -and $identifier -ne $PreviousId) {
                $candidate = Get-Process -Id $identifier -ErrorAction SilentlyContinue
                if ($candidate -and $candidate.Path -ieq (Join-Path $installed 'Freehand.App.exe')) { return $candidate }
            }
        }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $limit)
    throw "Isolated app did not become ready or restart. Fixture: $fixture"
}
function Start-IsolatedHost {
    $start = [Diagnostics.ProcessStartInfo]::new((Join-Path $installed 'Freehand.App.exe'))
    $start.UseShellExecute = $false; $start.CreateNoWindow = $true; $start.WindowStyle = 'Hidden'
    $start.ArgumentList.Add('--tray')
    $start.Environment['FREEHAND_DATA_DIRECTORY'] = $testProfile
    $start.Environment['FREEHAND_UPDATE_HANDOFF_TEST'] = '1'
    $process = [Diagnostics.Process]::Start($start)
    $process.Dispose()
    return Wait-IsolatedHost
}
function Stop-IsolatedHost {
    $ready = Join-Path $testProfile 'update-handoff.pid'
    if (-not (Test-Path -LiteralPath $ready)) { return }
    $identifier = 0
    if (-not [int]::TryParse((Get-Content -LiteralPath $ready -Raw).Trim(), [ref]$identifier)) { return }
    $process = Get-Process -Id $identifier -ErrorAction SilentlyContinue
    if ($process -and $process.Path -ieq (Join-Path $installed 'Freehand.App.exe')) {
        # Only the explicitly scoped headless fixture can be stopped here.
        $process.Kill($true); $process.WaitForExit(); $process.Dispose()
    }
}
function New-FixturePackage([string]$Version) {
    $manifest.Version = $Version
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath
    $path = Join-Path $fixture "Freehand-$Version-win-x64-Setup.exe"
    New-FreehandInstaller -PublishDirectory $payload -Runtime $runtime -Destination $path
    return $path
}
function Assert-Installation([string]$Version) {
    $actual = Get-Content -LiteralPath (Join-Path $installed 'package-manifest.json') -Raw | ConvertFrom-Json
    if ($actual.Version -cne $Version) { throw "Expected installed version $Version, got $($actual.Version)." }
    foreach ($name in $before.Keys) {
        if ((Get-FileHash -LiteralPath (Join-Path $testProfile $name)).Hash -cne $before[$name]) { throw "Update changed $name." }
    }
}
$previousProfile = $env:FREEHAND_DATA_DIRECTORY
$succeeded = $false
try {
    $env:FREEHAND_DATA_DIRECTORY = $testProfile
    # Fixture versions exercise replacement with the real published app, model, and self-test.
    $first = New-FixturePackage '0.0.1'
    if ((Invoke-IsolatedSetup $first) -ne 0) { throw "Initial installation failed. See $testProfile/Freehand-setup-error.log" }
    Assert-Installation '0.0.1'
    $oldHost = Start-IsolatedHost
    Set-Content -LiteralPath (Join-Path $installed 'obsolete.txt') -Value 'must disappear'
    $second = New-FixturePackage '0.0.2'
    if ((Invoke-IsolatedSetup $second -Update) -ne 0) { throw "Upgrade failed. See $testProfile/Freehand-setup-error.log" }
    if (-not $oldHost.WaitForExit(10000)) { throw 'Update did not stop the previous isolated app.' }
    $newHost = Wait-IsolatedHost $oldHost.Id
    $oldHost.Dispose()
    Assert-Installation '0.0.2'
    if (Test-Path -LiteralPath (Join-Path $installed 'obsolete.txt')) { throw 'Upgrade retained obsolete application files.' }
    Write-Output 'Passed: running 0.0.1 -> 0.0.2 update stopped and restarted the app and preserved user data.'

    $corrupt = Join-Path $fixture 'corrupt.exe'
    Copy-Item -LiteralPath $second -Destination $corrupt
    $file = [IO.File]::OpenWrite($corrupt)
    try { $file.Position = $file.Length - 1; $file.WriteByte(0) } finally { $file.Dispose() }
    if ((Invoke-IsolatedSetup $corrupt) -eq 0) { throw 'Corrupt payload was accepted.' }
    Assert-Installation '0.0.2'
    Write-Output 'Passed: corrupt payload left the installed version intact.'

    # A correctly hashed package with broken speech must fail installed verification and roll back.
    $speechFixture = Join-Path $payload 'fixtures/jfk.wav'
    [IO.File]::WriteAllBytes($speechFixture, [byte[]]::new(64))
    $entry = $manifest.Files | Where-Object { $_.Path.Replace('\', '/') -ceq 'fixtures/jfk.wav' }
    $entry.Size = 64; $entry.Sha256 = (Get-FileHash -LiteralPath $speechFixture -Algorithm SHA256).Hash.ToLowerInvariant()
    $broken = New-FixturePackage '0.0.3'
    if ((Invoke-IsolatedSetup $broken -Update) -eq 0) { throw 'Broken speech package was accepted.' }
    if (-not $newHost.WaitForExit(10000)) { throw 'Rollback did not stop the previous isolated app.' }
    $restoredHost = Wait-IsolatedHost $newHost.Id
    $newHost.Dispose(); $restoredHost.Dispose()
    Assert-Installation '0.0.2'
    Invoke-FreehandSelfTest (Join-Path $installed 'Freehand.App.exe')
    Write-Output 'Passed: failed installed self-test restored and restarted a working previous version.'
    $succeeded = $true
} finally {
    $env:FREEHAND_DATA_DIRECTORY = $previousProfile
    Stop-IsolatedHost
    # All generated files stay under this invocation's known artifacts directory.
    $boundary = [IO.Path]::GetFullPath((Join-Path $projectRoot 'artifacts/update-verification')) + [IO.Path]::DirectorySeparatorChar
    $resolved = [IO.Path]::GetFullPath($fixture)
    if ($succeeded -and $resolved.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $resolved -Recurse -Force }
    elseif (-not $succeeded) { Write-Warning "Failed update fixture and logs preserved at $fixture" }
}
