#Requires -Version 7.4
param([Parameter(Mandatory)][string]$Destination)
$ErrorActionPreference = 'Stop'
$version = '6.2.0'
$moduleDirectory = Join-Path $Destination "Pester/$version"
$manifest = Join-Path $moduleDirectory 'Pester.psd1'
if (Test-Path -LiteralPath $manifest) { return $manifest }

New-Item -ItemType Directory -Path $Destination -Force | Out-Null
$archive = Join-Path $Destination "pester.$version.nupkg"
if (-not (Test-Path -LiteralPath $archive)) {
    # Fetch the exact package without the Gallery's intermittent version-lookup endpoint.
    Invoke-WebRequest -Uri "https://www.powershellgallery.com/api/v2/package/Pester/$version" `
        -OutFile $archive -MaximumRetryCount 3 -RetryIntervalSec 2
}
$expectedHash = 'e6ac7418d4f12500269aaca58ae56cf1caafbbf1afa2cec334e289d1cf50a239'
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ine $expectedHash) {
    throw "Pinned Pester checksum failed. Remove $archive and retry."
}
[IO.Compression.ZipFile]::ExtractToDirectory($archive, $moduleDirectory, $true)
return $manifest
