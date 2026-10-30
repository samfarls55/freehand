using Freehand.Core;
using Shouldly;
using Xunit;

namespace Freehand.CoreTests;

public sealed class CleanupSettingsTests : IDisposable
{
    private readonly string _directory = Path.Combine(Path.GetTempPath(), "freehand-cleanup-settings-" + Guid.NewGuid().ToString("N"));
    private string SettingsPath => Path.Combine(_directory, "settings.json");

    [Fact]
    public void Legacy_preferences_enable_available_cleanup_without_changing_existing_values()
    {
        Directory.CreateDirectory(_directory);
        File.WriteAllText(SettingsPath, "{\"PushToTalkKey\":124,\"KeepHistory\":false,\"InjectText\":false}");
        var data = new AppSettings(SettingsPath).Data;
        data.CleanupEnabled.ShouldBeTrue();
        data.CleanupDirectory.ShouldBeNull();
        data.PushToTalkKey.ShouldBe(124);
        data.KeepHistory.ShouldBeFalse();
        data.InjectText.ShouldBeFalse();
    }

    [Fact]
    public void Explicit_cleanup_preference_and_selected_folder_survive_other_updates()
    {
        var settings = new AppSettings(SettingsPath);
        var selected = Path.Combine(_directory, "selected-cleanup");
        settings.TryUpdate(settings.Data with { CleanupEnabled = false, CleanupDirectory = selected }).ShouldBeTrue();
        var reopened = new AppSettings(SettingsPath);
        reopened.TryUpdate(reopened.Data with { KeepHistory = false }).ShouldBeTrue();
        var persisted = new AppSettings(SettingsPath).Data;
        persisted.CleanupEnabled.ShouldBeFalse();
        persisted.CleanupDirectory.ShouldBe(selected);
        persisted.KeepHistory.ShouldBeFalse();
    }

    [Fact]
    public void Empty_legacy_cleanup_folder_uses_the_bundled_selection()
    {
        Directory.CreateDirectory(_directory);
        File.WriteAllText(SettingsPath, "{\"CleanupEnabled\":false,\"CleanupDirectory\":\"   \"}");
        var data = new AppSettings(SettingsPath).Data;
        data.CleanupEnabled.ShouldBeFalse();
        data.CleanupDirectory.ShouldBeNull();
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory)) Directory.Delete(_directory, true);
    }
}
