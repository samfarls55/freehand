#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$OutputDirectory,
    [string]$RuntimeArchive
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$manifestPath = Join-Path $PSScriptRoot '../../packaging/accuracy-runtime-manifest.json'
$spec = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$output = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($OutputDirectory))
$files = @($spec.Files | ForEach-Object {
    [pscustomobject]@{ Name = $_.Name; Size = $_.Size; Sha256 = $_.Sha256 }
}) + @($spec.Licenses | ForEach-Object {
    [pscustomobject]@{ Name = 'licenses/' + $_.Name; Size = $_.Size; Sha256 = $_.Sha256 }
})

function Assert-PinnedRuntime {
    foreach ($file in $files) {
        $path = Join-Path $output $file.Name
        if ((Get-Item -LiteralPath $path).Length -ne $file.Size -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ine $file.Sha256) {
            throw "Official runtime checksum failed: $($file.Name)"
        }
    }
}

if (@($files | Where-Object { -not (Test-Path -LiteralPath (Join-Path $output $_.Name) -PathType Leaf) }).Count -eq 0) {
    Assert-PinnedRuntime
    Write-Output "Verified official runtime: $output"
    return
}

New-Item -ItemType Directory -Path $output -Force | Out-Null
if ($RuntimeArchive) {
    $archive = (Resolve-Path -LiteralPath $RuntimeArchive).Path
} else {
    $downloads = Join-Path $output '_downloads'
    New-Item -ItemType Directory -Path $downloads -Force | Out-Null
    $archive = Join-Path $downloads 'runtime.tar.gz'
    if (-not (Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest -Uri $spec.RuntimeArchive -OutFile $archive
    }
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ine $spec.RuntimeArchiveSha256) {
    throw 'Official runtime archive checksum failed.'
}
$members = @($files | ForEach-Object { "$($spec.RuntimePrefix)/$($_.Name)" })
& tar -xzf $archive -C $output --strip-components=1 @members
if ($LASTEXITCODE -ne 0) { throw 'Official runtime extraction failed.' }
Assert-PinnedRuntime
Write-Output "Prepared official runtime: $output"
