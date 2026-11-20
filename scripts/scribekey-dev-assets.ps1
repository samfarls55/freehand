#Requires -Version 7.0
# Shared acquisition checks, also exercised without launching Windows binaries.
function Assert-ScribeKeyFile([string]$Path, [long]$Size, [string]$Sha256) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing asset: $Path. Run git lfs pull." }
    $file = Get-Item -LiteralPath $Path -Force
    if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        ($Size -gt 0 -and $file.Length -ne $Size) -or
        (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ine $Sha256) {
        throw "Asset verification failed: $Path. Run git lfs pull for model weights; preserve or repair a corrupt download cache."
    }
}

function Get-ScribeKeyDownload([string]$Url, [string]$Path, [string]$Sha256, [long]$Size) {
    if (-not (Test-Path -LiteralPath $Path)) {
        $partial = $Path + '.' + [guid]::NewGuid().ToString('N') + '.partial'
        Invoke-WebRequest -Uri $Url -OutFile $partial -TimeoutSec 1800
        Assert-ScribeKeyFile $partial $Size $Sha256
        [IO.File]::Move($partial,$Path)
    }
    Assert-ScribeKeyFile $Path $Size $Sha256
}
