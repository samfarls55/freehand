#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $root 'scripts/scribekey-dev-assets.ps1')
$temp = Join-Path ([IO.Path]::GetTempPath()) ('freehand-scribekey-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp | Out-Null
function Assert-Rejected([scriptblock]$Action) {
    $rejected = $false
    try { & $Action } catch { $rejected = $true }
    if (-not $rejected) { throw 'Expected corrupt or missing artifact to be rejected.' }
}
try {
    $fixture = Join-Path $temp 'fixture.gguf'
    [IO.File]::WriteAllText($fixture,'verified-fixture')
    $size = (Get-Item $fixture).Length
    $hash = (Get-FileHash $fixture).Hash
    Assert-ScribeKeyFile $fixture $size $hash
    Assert-Rejected { Assert-ScribeKeyFile $fixture ($size + 1) $hash }
    [IO.File]::WriteAllText($fixture,'modified-fixture')
    Assert-Rejected { Assert-ScribeKeyFile $fixture $size $hash }
    Assert-Rejected { Assert-ScribeKeyFile (Join-Path $temp 'missing') $size $hash }
    [IO.File]::WriteAllText($fixture,"version https://git-lfs.github.com/spec/v1`n")
    Assert-Rejected { Assert-ScribeKeyFile $fixture 211804448 $hash }
    $assetRoot = Join-Path $root 'packaging/scribekey-dev'
    Assert-ScribeKeyFile (Join-Path $assetRoot 'assets/base-IQ4_XS.gguf') 211804448 '82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174'
    Assert-ScribeKeyFile (Join-Path $assetRoot 'assets/blend-t050-F32.gguf') 12006240 '4d14e22826d039a12444236124459363f02e77de247117b7b8379ccfe257cfb1'
    $cleanupProfile = Get-Content (Join-Path $assetRoot 'cleanup-profile.json') -Raw | ConvertFrom-Json
    if ($cleanupProfile.adapterScale -ne 1 -or $cleanupProfile.promptStyle -cne 'ScribeKeyFast' -or
        $cleanupProfile.specialistLiteralProtocol -cne 'CompactV3' -or -not $cleanupProfile.maskSpecialistLiterals -or
        $cleanupProfile.threads -ne 4 -or $cleanupProfile.gpuLayers -ne 0 -or $cleanupProfile.repack -or
        $cleanupProfile.batchSize -ne 64 -or $cleanupProfile.microBatchSize -ne 64 -or
        $cleanupProfile.cacheTypeK -cne 'f16' -or $cleanupProfile.cacheTypeV -cne 'f16' -or
        $cleanupProfile.promptLookupTokens -ne 16 -or $cleanupProfile.promptLookupMatchTokens -ne 3 -or
        $cleanupProfile.contextSize -ne 1024 -or $cleanupProfile.maxOutputTokens -ne 512 -or
        $cleanupProfile.promptCacheMiB -ne 0 -or $cleanupProfile.contextCheckpoints -ne 0) { throw 'Selected development profile drifted.' }
    foreach ($path in @('scripts/dev-scribekey.ps1','scripts/scribekey-dev-assets.ps1','packaging/scribekey-dev/Start Freehand ScribeKey Dev.ps1')) {
        $tokens = $null; $errors = $null
        $null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $root $path),[ref]$tokens,[ref]$errors)
        if ($errors.Count) { throw "PowerShell parse failed: $path" }
    }
    Write-Output 'ScribeKey dev: exact LFS assets/profile, corruption/missing/pointer rejection and PowerShell parsing PASS.'
} finally { Remove-Item -LiteralPath $temp -Recurse -Force }
