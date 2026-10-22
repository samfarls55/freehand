param([ValidateRange(1024, 65535)][int]$Port = 65003)
$ErrorActionPreference = 'Stop'
$nodePath = (Get-Command node -ErrorAction Stop).Source
& $nodePath (Join-Path $PSScriptRoot 'preview-design.mjs') --port $Port
exit $LASTEXITCODE
