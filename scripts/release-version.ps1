#Requires -Version 7.0
param()
. (Join-Path $PSScriptRoot 'common.ps1')

function ConvertTo-FreehandReleaseVersion([string]$Tag) {
    if ($Tag -cmatch '^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$') {
        $value = $null
        if ([version]::TryParse($Tag.Substring(1), [ref]$value) -and $value.Major -le 65534 -and $value.Minor -le 65534 -and $value.Build -le 65534) { return $value }
    }
}

# The workflow fetches all tags and serializes main runs, including publication.
$baseline = [version](Get-FreehandVersion)
$tags = @(git tag --list 'v*')
if ($LASTEXITCODE -ne 0) { throw 'Cannot read version tags.' }
$existing = @(git tag --points-at HEAD | ForEach-Object { ConvertTo-FreehandReleaseVersion $_ } | Sort-Object -Descending)
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify an existing release for this commit.' }
if ($existing.Count -gt 1) { throw 'More than one release version points to this commit.' }
if ($existing.Count -eq 1) { $next = $existing[0] }
else {
    $highest = @($tags | ForEach-Object { ConvertTo-FreehandReleaseVersion $_ } | Sort-Object -Descending | Select-Object -First 1)
    $next = $baseline
    if ($highest.Count -gt 0 -and $highest[0] -ge $baseline) {
        if ($highest[0].Build -eq 65534) { throw 'Patch version exhausted. Increase the minor version in Version.props.' }
        $next = [version]::new($highest[0].Major, $highest[0].Minor, $highest[0].Build + 1)
    }
}
Write-Output $next.ToString(3)
