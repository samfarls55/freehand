using Freehand.Platform.Windows;
using Microsoft.Win32;
using Xunit;

namespace Freehand.Windows.Tests;

public sealed class DevelopmentProfileTests
{
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void Isolated_profile_does_not_change_installed_login_startup(bool enabled)
    {
        var previousProfile = Environment.GetEnvironmentVariable("FREEHAND_DATA_DIRECTORY");
        const string startupPath = "Software\\Microsoft\\Windows\\CurrentVersion\\Run";
        using var startup = Registry.CurrentUser.OpenSubKey(startupPath);
        var original = startup?.GetValue("Freehand");
        var originalKind = original is null ? RegistryValueKind.String : startup!.GetValueKind("Freehand");
        try
        {
            Environment.SetEnvironmentVariable("FREEHAND_DATA_DIRECTORY", Path.GetTempPath());
            using var desktop = new WindowsDesktopIntegration();
            desktop.SetLoginStartup(enabled);
            using var after = Registry.CurrentUser.OpenSubKey(startupPath);
            Assert.Equal(original, after?.GetValue("Freehand"));
        }
        finally
        {
            Environment.SetEnvironmentVariable("FREEHAND_DATA_DIRECTORY", previousProfile);
            // Restore only if a regression changed the entry during this test.
            using var restore = Registry.CurrentUser.OpenSubKey(startupPath, writable: true);
            if (restore is not null && !Equals(original, restore.GetValue("Freehand")))
            {
                if (original is null) restore.DeleteValue("Freehand", throwOnMissingValue: false);
                else restore.SetValue("Freehand", original, originalKind);
            }
        }
    }
}
