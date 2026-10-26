Describe 'Published update handoff' {
    It 'updates and rolls back a running isolated app without changing user data' {
        $scriptPath = Join-Path $env:FREEHAND_SCRIPT_TEST_ROOT 'scripts/verify-updates.ps1'
        $output = & $scriptPath -PublishDirectory $env:FREEHAND_VERIFIED_PUBLISH -InstallerRuntime $env:FREEHAND_VERIFIED_INSTALLER
        ($output -contains 'Passed: running 0.0.1 -> 0.0.2 update stopped and restarted the app and preserved user data.') | Should-BeTrue
        ($output -contains 'Passed: failed installed self-test restored and restarted a working previous version.') | Should-BeTrue
    }
    It 'keeps setup diagnostics when verification fails unexpectedly' {
        $payload = Join-Path $TestDrive 'incomplete-payload'
        New-Item -ItemType Directory -Path $payload | Out-Null
        @{ Version = '0.0.0'; Build = 'incomplete-fixture'; Files = @() } | ConvertTo-Json |
            Set-Content -LiteralPath (Join-Path $payload 'package-manifest.json')
        $scriptPath = Join-Path $env:FREEHAND_SCRIPT_TEST_ROOT 'scripts/verify-updates.ps1'
        { & $scriptPath -PublishDirectory $payload -InstallerRuntime $env:FREEHAND_VERIFIED_INSTALLER } | Should-Throw '*Initial installation failed*'
        $parent = Join-Path $env:FREEHAND_SCRIPT_TEST_ROOT 'artifacts/update-verification'
        $failed = @(Get-ChildItem -LiteralPath $parent -Directory)
        $failed.Count | Should-Be 1
        Test-Path -LiteralPath (Join-Path $failed[0].FullName 'data/Freehand-setup-error.log') | Should-BeTrue
        # The retention assertion is complete; remove only this test's known fixture.
        if ($failed[0].FullName.StartsWith([IO.Path]::GetFullPath($parent) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $failed[0].FullName -Recurse -Force
        }
    }
}
