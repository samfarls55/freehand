#Requires -Version 7.4
param()
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$tools = Join-Path $repositoryRoot 'artifacts/test-tools'
$pester = Join-Path $tools 'Pester/6.2.0/Pester.psd1'
if (-not (Test-Path -LiteralPath $pester)) {
    Save-PSResource -Name Pester -Version 6.2.0 -Path $tools -Repository PSGallery -TrustRepository
}
Import-Module $pester -Force
$fixture = Join-Path $repositoryRoot ('artifacts/script-fixtures/' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $fixture 'scripts') -Force | Out-Null
Copy-Item -Path (Join-Path $repositoryRoot 'scripts/*.ps1') -Destination (Join-Path $fixture 'scripts')
$coverage = Join-Path $repositoryRoot 'artifacts/coverage'
New-Item -ItemType Directory -Path $coverage -Force | Out-Null
$previousFixture = $env:FREEHAND_SCRIPT_TEST_ROOT
try {
    $env:FREEHAND_SCRIPT_TEST_ROOT = $fixture
    $config = New-PesterConfiguration
    $config.Run.Path = Join-Path $PSScriptRoot 'Deployment.Tests.ps1'
    $config.Run.PassThru = $true
    $config.Output.Verbosity = 'Detailed'
    $config.CodeCoverage.Enabled = $true
    $config.CodeCoverage.Path = Join-Path $fixture 'scripts/*.ps1'
    $config.CodeCoverage.ReportRoot = $fixture
    $config.CodeCoverage.OutputFormat = 'Cobertura'
    $config.CodeCoverage.OutputPath = Join-Path $coverage 'scripts.cobertura.xml'
    $result = Invoke-Pester -Configuration $config
    # Map the unchanged copies' relative paths back to the repository sources.
    [xml]$inputReport = Get-Content -LiteralPath $config.CodeCoverage.OutputPath.Value -Raw
    $outputReport = [xml]'<coverage version="1" />'
    foreach ($source in $inputReport.coverage.packages.package.classes.class) {
        $file = $outputReport.CreateElement('file')
        $file.SetAttribute('path', $source.filename.Replace('\', '/'))
        foreach ($sourceLine in $source.lines.line) {
            $line = $outputReport.CreateElement('lineToCover')
            $line.SetAttribute('lineNumber', $sourceLine.number)
            $line.SetAttribute('covered', ([int]$sourceLine.hits -gt 0).ToString().ToLowerInvariant())
            [void]$file.AppendChild($line)
        }
        [void]$outputReport.DocumentElement.AppendChild($file)
    }
    $outputReport.Save((Join-Path $coverage 'scripts.xml'))
    if ($result.FailedCount -gt 0 -or $result.FailedContainersCount -gt 0) { throw 'Deployment script regression tests failed.' }
} finally { $env:FREEHAND_SCRIPT_TEST_ROOT = $previousFixture }
