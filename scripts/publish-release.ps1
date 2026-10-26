#Requires -Version 7.0
param([Parameter(Mandatory)][string]$Version, [Parameter(Mandatory)][string]$Commit)
. (Join-Path $PSScriptRoot 'common.ps1')
if ($Version -cnotmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$' -or $Commit -notmatch '^[a-f0-9]{40}$') { throw 'Invalid release identity.' }
$tag = "v$Version"
$installer = Join-Path $projectRoot "artifacts/release/Freehand-$Version-win-x64-Setup.exe"
$checksum = $installer + '.sha256'
if (-not (Test-Path -LiteralPath $installer) -or -not (Test-Path -LiteralPath $checksum)) { throw 'Verified release assets are missing.' }
$expected = ((Get-Content -LiteralPath $checksum -Raw).Trim() -split '\s+')[0]
if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ine $expected) { throw 'Release checksum failed.' }
$main = gh api "repos/$env:GITHUB_REPOSITORY/commits/main" --jq .sha
if ($LASTEXITCODE -ne 0 -or $main -notmatch '^[a-f0-9]{40}$') { throw 'Cannot confirm the current main commit.' }
if ($main -cne $Commit) {
    git fetch origin $main
    if ($LASTEXITCODE -ne 0) { throw 'Cannot fetch the current main commit.' }
    git merge-base --is-ancestor $Commit $main
    if ($LASTEXITCODE -eq 1) { Write-Output 'This build is no longer on main; publication was skipped.'; return }
    if ($LASTEXITCODE -ne 0) { throw 'Cannot check main ancestry.' }
    # Match the Windows workflow paths. A docs-only merge has no replacement build.
    $paths = @('src/**', 'tests/**', 'shared/**', 'packaging/**', 'scripts/**', '*.props', '*.sln', '*.slnf', 'global.json', '.github/workflows/windows.yml') |
        ForEach-Object { ':(top,glob)' + $_ }
    $changed = @(git diff --name-only $Commit $main -- @paths)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect changes after this build.' }
    if ($changed.Count -gt 0) { Write-Output 'A newer application commit superseded this build; publication was skipped.'; return }
}
# Check existence through a successful listing, so API failures never look like a missing release.
$releasesJson = gh api "repos/$env:GITHUB_REPOSITORY/releases?per_page=100" --paginate --slurp
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect existing releases.' }
$pages = ConvertFrom-Json -InputObject ($releasesJson -join "`n") -NoEnumerate
$existing = @(foreach ($page in $pages) { foreach ($release in $page) { if ($release.tag_name -ceq $tag) { $release } } })
if ($existing.Count -gt 1) { throw 'Ambiguous release tag.' }
if ($existing.Count -eq 1) {
    $remoteCommit = gh api "repos/$env:GITHUB_REPOSITORY/commits/$tag" --jq .sha
    if ($LASTEXITCODE -ne 0 -or $remoteCommit -cne $Commit) { throw 'Existing release belongs to a different commit.' }
    if (-not $existing[0].draft) { Write-Output "$tag is already published; its assets were left unchanged."; return }
}
# Reserve the version before any upload. A failed draft must not block the next main commit.
$tags = @(git tag --list $tag)
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the release tag.' }
if ($tags.Count -gt 0) {
    $tagCommit = git rev-parse "$tag^{commit}"
    if ($LASTEXITCODE -ne 0 -or $tagCommit -cne $Commit) { throw 'Release tag belongs to a different commit.' }
} else {
    git tag $tag $Commit
    if ($LASTEXITCODE -ne 0) { throw 'Cannot reserve the release tag.' }
    git push origin "refs/tags/$tag"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot push the release tag.' }
}
if ($existing.Count -eq 1) { gh release upload $tag $installer $checksum --clobber }
else { gh release create $tag $installer $checksum --draft --verify-tag --title "Freehand $Version" --generate-notes }
if ($LASTEXITCODE -ne 0) { throw 'Release asset upload failed. Nothing was published.' }
# Re-read the draft and verify both uploads before making it visible to installed apps.
$draftJson = gh release view $tag --json assets,isDraft
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify the draft release.' }
$draft = $draftJson | ConvertFrom-Json
if (-not $draft.isDraft) { throw 'The release is no longer a draft. Its assets were left unchanged.' }
foreach ($path in @($installer, $checksum)) {
    $asset = @($draft.assets | Where-Object name -CEQ ([IO.Path]::GetFileName($path)))
    if ($asset.Count -ne 1 -or $asset[0].size -ne (Get-Item -LiteralPath $path).Length) { throw 'Release asset verification failed.' }
}
gh release edit $tag --draft=false --latest
if ($LASTEXITCODE -ne 0) { throw 'Release publication failed.' }
