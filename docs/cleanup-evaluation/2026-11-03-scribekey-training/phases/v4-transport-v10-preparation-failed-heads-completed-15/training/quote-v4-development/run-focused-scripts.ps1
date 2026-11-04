param([Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Preserve prior test evidence; choose a new directory.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$repository = '/workspace/freehand'
Import-Module '/workspace/freehand/artifacts/test-tools/Pester/6.2.0/Pester.psd1' -Force
$previous = $env:FREEHAND_SCRIPT_TEST_ROOT
try {
    $env:FREEHAND_SCRIPT_TEST_ROOT = Join-Path $OutputDirectory 'fixture'
    $configuration = New-PesterConfiguration
    $configuration.Run.Path = @((Join-Path $repository 'tests/Freehand.Scripts.Tests/Cleanup.Tests.ps1'), (Join-Path $repository 'tests/Freehand.Scripts.Tests/CleanupAcquisition.Tests.ps1'))
    $configuration.Run.PassThru = $true
    $configuration.Output.Verbosity = 'Detailed'
    $configuration.TestResult.Enabled = $true
    $configuration.TestResult.OutputFormat = 'NUnitXml'
    $configuration.TestResult.OutputPath = Join-Path $OutputDirectory 'results.xml'
    $result = Invoke-Pester -Configuration $configuration
    @{ Total = $result.TotalCount; Passed = $result.PassedCount; Failed = $result.FailedCount; Skipped = $result.SkippedCount; FailedContainers = $result.FailedContainersCount } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'summary.json')
    if ($result.FailedCount -gt 0 -or $result.FailedContainersCount -gt 0) { throw 'Affected script regression tests failed.' }
} finally { $env:FREEHAND_SCRIPT_TEST_ROOT = $previous }
