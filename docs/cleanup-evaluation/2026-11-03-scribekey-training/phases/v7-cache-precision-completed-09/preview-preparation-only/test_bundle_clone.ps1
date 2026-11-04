#Requires -Version 5.1
# Synthetic bytes only. Import function definitions; never execute the Windows launcher body.
$ErrorActionPreference = 'Stop'
$tokens = $null; $parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'run-preview.ps1'), [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) { throw 'Launcher PowerShell parse failed.' }
foreach ($function in $ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
    Invoke-Expression $function.Extent.Text
}
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('freehand-native-lora-synthetic-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$source = Join-Path $testRoot 'source'; New-Item -ItemType Directory -Path $source | Out-Null
$checks = 0
function Assert-Fails([scriptblock]$Action) {
    $failed = $false
    try { & $Action } catch { $failed = $true }
    if (-not $failed) { throw 'Expected synthetic rejection did not occur.' }
    $script:checks++
}
try {
    $files = @()
    foreach ($relative in @('runtime/llama-server.exe', 'model.gguf', 'adapter.gguf', 'licenses/model-LICENSE.txt', 'licenses/runtime-LICENSE.txt')) {
        $path = Join-Path $source $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
        [IO.File]::WriteAllText($path, 'synthetic-only:' + $relative, (New-Object Text.UTF8Encoding($false)))
        $files += @{ path = $relative; size = (Get-Item -LiteralPath $path).Length; sha256 = Get-PreviewHash $path }
    }
    $manifest = [ordered]@{ schemaVersion = 1; platform = 'win-x64-vulkan'; runtimePath = 'runtime/llama-server.exe'
        runtimeSha256 = Get-PreviewHash (Join-Path $source 'runtime/llama-server.exe'); modelPath = 'model.gguf'
        modelSha256 = Get-PreviewHash (Join-Path $source 'model.gguf'); adapterPath = 'adapter.gguf'
        adapterSha256 = Get-PreviewHash (Join-Path $source 'adapter.gguf'); adapterScale = 1; cacheTypeK = 'f32'; cacheTypeV = 'f32'; files = $files }
    $manifestPath = Join-Path $source 'cleanup-manifest.json'; Write-PreviewJson $manifestPath $manifest
    $originalManifest = Get-PreviewHash $manifestPath
    $result = Copy-VerifiedPreviewBundle $source (Join-Path $testRoot 'cloned')
    if ($result.Manifest.adapterScale -ne 1 -or $result.Manifest.adapterSha256 -ine $manifest.adapterSha256 -or
        $result.Manifest.cacheTypeK -cne 'f32' -or $result.Manifest.cacheTypeV -cne 'f32' -or
        (Get-PreviewHash (Join-Path $testRoot 'cloned/adapter.gguf')) -ine $manifest.adapterSha256 -or
        (Get-PreviewHash $manifestPath) -ine $originalManifest) { throw 'Synthetic clone failed pair/source preservation.' }
    $checks++
    $manifest.adapterScale = 0.5; Write-PreviewJson $manifestPath $manifest
    Assert-Fails { Copy-VerifiedPreviewBundle $source (Join-Path $testRoot 'nonunit') }
    $manifest.adapterScale = 1; $correct = $manifest.adapterSha256; $manifest.adapterSha256 = 'a' * 64; Write-PreviewJson $manifestPath $manifest
    Assert-Fails { Copy-VerifiedPreviewBundle $source (Join-Path $testRoot 'bad-pin') }
    $manifest.adapterSha256 = $correct; $manifest.adapterPath = '../adapter.gguf'; Write-PreviewJson $manifestPath $manifest
    Assert-Fails { Copy-VerifiedPreviewBundle $source (Join-Path $testRoot 'escape') }
    $manifest.adapterPath = 'adapter.gguf'; $manifest.Remove('adapterPath'); Write-PreviewJson $manifestPath $manifest
    Assert-Fails { Copy-VerifiedPreviewBundle $source (Join-Path $testRoot 'orphan') }
    $manifest.adapterPath = 'adapter.gguf'; $manifest.files = @($files) + @{path = 'ADAPTER.GGUF'; size = $files[2].size; sha256 = $files[2].sha256}; Write-PreviewJson $manifestPath $manifest
    Assert-Fails { Copy-VerifiedPreviewBundle $source (Join-Path $testRoot 'case-collision') }
    [pscustomobject]@{ ChecksPassed = $checks; SyntheticBytesOnly = $true; DotNetOrNativeExecuted = $false
        WindowsExecuted = $false; LauncherParsed = $true; FunctionsOnly = $true } | ConvertTo-Json
} finally { Remove-Item -LiteralPath $testRoot -Recurse -Force }
