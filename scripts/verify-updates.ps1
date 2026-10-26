#Requires -Version 7.0
param()
. (Join-Path $PSScriptRoot 'common.ps1')
$fixture = Join-Path $projectRoot ('artifacts/update-verification/' + [guid]::NewGuid().ToString('N'))
$payload = Join-Path $fixture 'payload'
$installed = Join-Path $fixture 'installed'
$profile = Join-Path $fixture 'data'
$runtime = Join-Path $projectRoot 'artifacts/installer-runtime/Freehand.Installer.exe'
if (-not (Test-Path -LiteralPath $runtime)) { throw 'Run verify.ps1 -Package first.' }
New-Item -ItemType Directory -Path $payload, $profile -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $projectRoot 'artifacts/publish') | Copy-Item -Destination $payload -Recurse
$manifestPath = Join-Path $payload 'package-manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
foreach ($name in @('settings.json', 'dictionary.txt', 'transcripts.jsonl')) {
    Set-Content -LiteralPath (Join-Path $profile $name) -Value ('preserved-' + $name)
}
$before = @{}
Get-ChildItem -LiteralPath $profile -File | ForEach-Object { $before[$_.Name] = (Get-FileHash -LiteralPath $_.FullName).Hash }

function Invoke-IsolatedSetup([string]$Path) {
    $start = [Diagnostics.ProcessStartInfo]::new($Path)
    $start.UseShellExecute = $false; $start.CreateNoWindow = $true; $start.WindowStyle = 'Hidden'
    foreach ($argument in @('--quiet', '--isolated', '--directory', $installed)) { $start.ArgumentList.Add($argument) }
    $start.Environment['FREEHAND_DATA_DIRECTORY'] = $profile
    $process = [Diagnostics.Process]::Start($start)
    try {
        if (-not $process.WaitForExit(240000)) { $process.Kill($true); throw 'Isolated setup timed out.' }
        return $process.ExitCode
    } finally { $process.Dispose() }
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
        if ((Get-FileHash -LiteralPath (Join-Path $profile $name)).Hash -cne $before[$name]) { throw "Update changed $name." }
    }
}
$previousProfile = $env:FREEHAND_DATA_DIRECTORY
try {
    $env:FREEHAND_DATA_DIRECTORY = $profile
    # Fixture versions exercise replacement with the real published app, model, and self-test.
    $first = New-FixturePackage '0.0.1'
    if ((Invoke-IsolatedSetup $first) -ne 0) { throw "Initial installation failed. See $profile/Freehand-setup-error.log" }
    Assert-Installation '0.0.1'
    Set-Content -LiteralPath (Join-Path $installed 'obsolete.txt') -Value 'must disappear'
    $second = New-FixturePackage '0.0.2'
    if ((Invoke-IsolatedSetup $second) -ne 0) { throw "Upgrade failed. See $profile/Freehand-setup-error.log" }
    Assert-Installation '0.0.2'
    if (Test-Path -LiteralPath (Join-Path $installed 'obsolete.txt')) { throw 'Upgrade retained obsolete application files.' }
    Write-Output 'Passed: isolated 0.0.1 -> 0.0.2 upgrade preserved settings, dictionary, and history.'

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
    if ((Invoke-IsolatedSetup $broken) -eq 0) { throw 'Broken speech package was accepted.' }
    Assert-Installation '0.0.2'
    Invoke-FreehandSelfTest (Join-Path $installed 'Freehand.App.exe')
    Write-Output 'Passed: failed installed self-test restored a working previous version.'
} finally {
    $env:FREEHAND_DATA_DIRECTORY = $previousProfile
    # All generated files stay under this invocation's known artifacts directory.
    $boundary = [IO.Path]::GetFullPath((Join-Path $projectRoot 'artifacts/update-verification')) + [IO.Path]::DirectorySeparatorChar
    $resolved = [IO.Path]::GetFullPath($fixture)
    if ($resolved.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}
