#Requires -Version 7.0
[CmdletBinding()]
param([switch]$Benchmark, [switch]$SelfTest)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'This preview requires Windows x64 and PowerShell 7.' }
if ($Benchmark -and $SelfTest) { throw 'Choose Benchmark or SelfTest.' }
if (-not $SelfTest -and (Get-Process -Name Freehand.App -ErrorAction SilentlyContinue)) {
    throw 'Quit Freehand from its tray menu before starting this preview.'
}
$app = Join-Path $PSScriptRoot 'app'
$dataDirectory = Join-Path $PSScriptRoot $(if ($SelfTest) { 'selftest-profile' } else { 'profile' })
New-Item -ItemType Directory -Force -Path $dataDirectory | Out-Null
$settingsPath = Join-Path $dataDirectory 'settings.json'
$settings = if (Test-Path $settingsPath) { Get-Content $settingsPath -Raw | ConvertFrom-Json -AsHashtable } else { @{} }
$settings.ModelDirectory = Join-Path $app 'models/parakeet-110m'
$settings.CleanupDirectory = Join-Path $app 'models/cleanup'
$settings.CleanupEnabled = $true
$settings.StartAtLogin = $false
$settings | ConvertTo-Json -Depth 8 | Set-Content $settingsPath -Encoding utf8NoBOM
$start = [Diagnostics.ProcessStartInfo]::new((Join-Path $app 'Freehand.App.exe'))
$start.UseShellExecute = $false
$start.WorkingDirectory = $app
$start.Environment['FREEHAND_DATA_DIRECTORY'] = $dataDirectory
$start.Environment['DOTNET_TieredPGO'] = '0'
foreach ($name in @('FREEHAND_MODEL_PROFILE','DOTNET_TieredCompilation','COMPlus_TieredCompilation','COMPlus_TieredPGO','LLAMA_ARG_DEVICE','GGML_VK_VISIBLE_DEVICES')) {
    $start.Environment.Remove($name) | Out-Null
}
if ($SelfTest) { $start.ArgumentList.Add('--selftest') }
if ($Benchmark) {
    $report = Join-Path $dataDirectory ('desktop-delivery-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '.json')
    $start.ArgumentList.Add('--desktop-delivery-benchmark')
    $start.ArgumentList.Add($report)
    $start.ArgumentList.Add('--include-cleanup')
    Write-Output "Benchmark report: $report"
}
$process = [Diagnostics.Process]::Start($start)
if ($SelfTest) {
    if (-not $process.WaitForExit(180000)) { $process.Kill($true); $process.WaitForExit(); throw 'Development self-test timed out.' }
    $global:LASTEXITCODE = $process.ExitCode
    if ($process.ExitCode -ne 0) { throw "Development self-test failed: $($process.ExitCode)" }
} elseif ($Benchmark) {
    $process.WaitForExit()
    $global:LASTEXITCODE = $process.ExitCode
    if ($process.ExitCode -ne 0) { throw "Development benchmark failed; inspect $report" }
} else {
    Write-Output "ScribeKey blend development app started: PID $($process.Id). Profile: $dataDirectory"
}
$process.Dispose()
