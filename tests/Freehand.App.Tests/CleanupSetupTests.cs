using Avalonia.Automation;
using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.Interactivity;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Freehand.App;
using Freehand.App.Views;
using Freehand.Cleanup;
using Freehand.Core;
using Shouldly;
using Xunit;

namespace Freehand.AppTests;

public sealed class CleanupSetupTests
{
    [AvaloniaFact]
    public async Task Settings_downloads_only_on_request_shows_progress_and_supports_cancel_then_retry()
    {
        using var data = new UiData();
        var initial = Path.Combine(Path.GetTempPath(), "existing-cleanup");
        data.Settings.Update(data.Settings.Data with { CleanupDirectory = initial });
        var calls = 0;
        IProgress<CleanupAssetProgress>? progress = null;
        var reloads = 0;
        var pending = new TaskCompletionSource<CleanupAssetInstallation>(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var setup = new CleanupSetupCoordinator(data.Settings, async (report, cancellation) =>
        {
            progress = report;
            if (Interlocked.Increment(ref calls) == 1) return await pending.Task.WaitAsync(cancellation);
            return Installed();
        }, () => reloads++, modelName: "Selected cleanup model", modelBytes: 5_800_000_000);
        var view = new SettingsView(data.Settings, null, null, cleanupSetup: setup);
        var window = new Window { Content = view, Width = 540, Height = 700 }; window.Show();
        try
        {
            data.Settings.Update(data.Settings.Data with { CleanupEnabled = false });
            data.Settings.Update(data.Settings.Data with { CleanupEnabled = true });
            window.UpdateLayout();
            calls.ShouldBe(0, "opening settings and changing preferences must never start a download");
            FindButton(view, "Set up cleanup").RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            await WaitUntilAsync(() => calls == 1);
            var running = setup.StartAsync();
            calls.ShouldBe(1, "a repeated action must share the active download");
            progress!.Report(new("Downloading cleanup model", 2_900_000_000, 5_800_000_000));
            await WaitUntilAsync(() => view.GetVisualDescendants().OfType<ProgressBar>().Single().Value == 50);
            FindButton(view, "Set up cleanup").IsEnabled.ShouldBeFalse();
            FindButton(view, "Use bundled cleanup").IsEnabled.ShouldBeFalse();
            FindButton(view, "Cancel setup").RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            await running;
            setup.Snapshot.Phase.ShouldBe(CleanupSetupPhase.Cancelled);
            data.Settings.Data.CleanupDirectory.ShouldBe(initial);
            reloads.ShouldBe(0);
            Dispatcher.UIThread.RunJobs();
            FindButton(view, "Retry setup").RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            await WaitUntilAsync(() => setup.Snapshot.Phase == CleanupSetupPhase.Installed);
            Dispatcher.UIThread.RunJobs();
            FindButton(view, "Check cleanup assets").IsEnabled.ShouldBeTrue();
            data.Settings.Data.CleanupDirectory.ShouldBe(Installed().DirectoryPath);
            reloads.ShouldBe(1);
        }
        finally { window.Close(); }
    }

    [AvaloniaFact]
    public async Task Verified_completion_preserves_latest_preferences_and_selects_on_the_ui_thread()
    {
        using var data = new UiData();
        var pending = new TaskCompletionSource<CleanupAssetInstallation>(TaskCreationOptions.RunContinuationsAsynchronously);
        var reloads = 0;
        var selectedOnUiThread = false;
        data.Settings.Changed += (_, _) => selectedOnUiThread = Dispatcher.UIThread.CheckAccess();
        await using var setup = new CleanupSetupCoordinator(data.Settings, (_, _) => pending.Task, () => reloads++);
        var running = setup.StartAsync();
        data.Settings.Update(data.Settings.Data with { CleanupEnabled = false, InjectText = false, KeepHistory = false });
        pending.SetResult(Installed());
        await running;
        var reopened = new AppSettings(data.SettingsPath);
        reopened.Data.CleanupDirectory.ShouldBe(Installed().DirectoryPath);
        reopened.Data.CleanupEnabled.ShouldBeFalse();
        reopened.Data.InjectText.ShouldBeFalse();
        reopened.Data.KeepHistory.ShouldBeFalse();
        selectedOnUiThread.ShouldBeTrue();
        reloads.ShouldBe(1);
        setup.Snapshot.Phase.ShouldBe(CleanupSetupPhase.Installed);
    }

    [AvaloniaFact]
    public async Task A_folder_selected_during_download_is_preserved()
    {
        using var data = new UiData();
        var pending = new TaskCompletionSource<CleanupAssetInstallation>(TaskCreationOptions.RunContinuationsAsynchronously);
        var reloads = 0;
        await using var setup = new CleanupSetupCoordinator(data.Settings, (_, _) => pending.Task, () => reloads++);
        var running = setup.StartAsync();
        var chosen = Path.Combine(Path.GetTempPath(), "newer-custom-cleanup");
        data.Settings.Update(data.Settings.Data with { CleanupDirectory = chosen });
        pending.SetResult(Installed());
        await running;
        data.Settings.Data.CleanupDirectory.ShouldBe(chosen);
        reloads.ShouldBe(0);
        setup.Snapshot.Phase.ShouldBe(CleanupSetupPhase.Installed);
        setup.Snapshot.Status.ShouldContain("current folder selection kept");
    }

    [AvaloniaFact]
    public async Task A_failed_download_preserves_the_override_and_can_be_retried()
    {
        using var data = new UiData();
        const string chosen = "existing-cleanup";
        data.Settings.Update(data.Settings.Data with { CleanupDirectory = chosen });
        var calls = 0;
        var reloads = 0;
        await using var setup = new CleanupSetupCoordinator(data.Settings, (_, _) =>
        {
            if (Interlocked.Increment(ref calls) == 1) throw new HttpRequestException("fixture network failure");
            return Task.FromResult(Installed());
        }, () => reloads++);
        await setup.StartAsync();
        setup.Snapshot.Phase.ShouldBe(CleanupSetupPhase.Failed);
        data.Settings.Data.CleanupDirectory.ShouldBe(chosen);
        reloads.ShouldBe(0);
        await setup.StartAsync();
        setup.Snapshot.Phase.ShouldBe(CleanupSetupPhase.Installed);
        reloads.ShouldBe(1);
    }

    [AvaloniaFact]
    public async Task A_failed_preference_save_does_not_claim_the_model_was_selected()
    {
        using var data = new UiData();
        var blocker = data.SettingsPath + ".parent-file";
        File.WriteAllText(blocker, "fixture");
        var settings = new AppSettings(Path.Combine(blocker, "settings.json"));
        var reloads = 0;
        await using var setup = new CleanupSetupCoordinator(settings, (_, _) => Task.FromResult(Installed()), () => reloads++);
        await setup.StartAsync();
        settings.Data.CleanupDirectory.ShouldBeNull();
        setup.Snapshot.Phase.ShouldBe(CleanupSetupPhase.Failed);
        setup.Snapshot.Status.ShouldContain("could not be saved");
        reloads.ShouldBe(0);
    }

    [AvaloniaFact]
    public async Task Disposing_cancels_owned_setup_and_ignores_late_success_or_progress()
    {
        using var data = new UiData();
        var started = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var pending = new TaskCompletionSource<CleanupAssetInstallation>(TaskCreationOptions.RunContinuationsAsynchronously);
        CancellationToken token = default;
        IProgress<CleanupAssetProgress>? progress = null;
        var reloads = 0;
        var changes = 0;
        var setup = new CleanupSetupCoordinator(data.Settings, (report, cancellation) =>
        {
            token = cancellation; progress = report; started.SetResult(true); return pending.Task;
        }, () => reloads++);
        setup.Changed += (_, _) => Interlocked.Increment(ref changes);
        var running = setup.StartAsync();
        await started.Task;
        var disposal = setup.DisposeAsync().AsTask();
        token.IsCancellationRequested.ShouldBeTrue();
        disposal.IsCompleted.ShouldBeFalse();
        var before = changes;
        progress!.Report(new("late progress", 1, 1));
        pending.SetResult(Installed());
        await disposal;
        await running;
        data.Settings.Data.CleanupDirectory.ShouldBeNull();
        changes.ShouldBe(before);
        reloads.ShouldBe(0);
    }

    [AvaloniaFact]
    public async Task Closing_settings_does_not_cancel_application_owned_setup()
    {
        using var data = new UiData();
        var pending = new TaskCompletionSource<CleanupAssetInstallation>(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var setup = new CleanupSetupCoordinator(data.Settings, (_, _) => pending.Task, () => { });
        var view = new SettingsView(data.Settings, null, null, cleanupSetup: setup);
        var window = new Window { Content = view }; window.Show();
        var running = setup.StartAsync();
        window.Close();
        pending.SetResult(Installed());
        await running;
        setup.Snapshot.Phase.ShouldBe(CleanupSetupPhase.Installed);
        data.Settings.Data.CleanupDirectory.ShouldBe(Installed().DirectoryPath);
    }

    [AvaloniaFact]
    public async Task Missing_setup_metadata_keeps_the_manual_folder_path_available()
    {
        using var data = new UiData();
        var calls = 0;
        await using var setup = new CleanupSetupCoordinator(data.Settings, (_, _) =>
        {
            calls++; return Task.FromResult(Installed());
        }, () => { }, isAvailable: false);
        var view = new SettingsView(data.Settings, null, null, cleanupSetup: setup);
        var window = new Window { Content = view }; window.Show();
        try
        {
            FindButton(view, "Set up cleanup").IsEnabled.ShouldBeFalse();
            FindButton(view, "Use bundled cleanup").IsEnabled.ShouldBeTrue();
            await setup.StartAsync();
            calls.ShouldBe(0);
        }
        finally { window.Close(); }
    }

    private static CleanupAssetInstallation Installed()
    {
        var directory = Path.Combine(Path.GetTempPath(), "verified-cleanup-assets");
        return new(directory, Path.Combine(directory, "cleanup-manifest.json"), "fixture-model");
    }

    private static Button FindButton(Control view, string text) => view.GetVisualDescendants().OfType<Button>()
        .Single(button => Equals(button.Content, text));

    private static async Task WaitUntilAsync(Func<bool> condition)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        while (!condition()) { await Task.Delay(10, timeout.Token); Dispatcher.UIThread.RunJobs(); }
    }
}
