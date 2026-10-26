using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.Interactivity;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Freehand.Abstractions;
using Freehand.App.Views;
using Freehand.Core.Updates;
using Shouldly;

namespace Freehand.AppTests;

public sealed class UpdateUiTests
{
    [AvaloniaFact]
    public async Task Update_offer_does_not_activate_and_waits_after_user_acceptance()
    {
        var source = new Source();
        await using var updates = new UpdateService(source, new Installer(), new Version(1, 0, 0), "unused", "unused", () => false);
        await updates.CheckAsync();
        var window = new UpdateWindow(updates); window.Show(); window.UpdateLayout();
        try
        {
            window.ShowActivated.ShouldBeFalse();
            window.GetVisualDescendants().OfType<TextBlock>().Any(t => t.Text == "Freehand 1.0.1 is available").ShouldBeTrue();
            source.Downloads.ShouldBe(0);
            UiCapture.Save(window, "compact-update-offer.png");
            window.GetVisualDescendants().OfType<Button>().Single(b => Equals(b.Content, "Update"))
                .RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            Dispatcher.UIThread.RunJobs(); window.UpdateLayout();
            source.Downloads.ShouldBe(1); updates.Snapshot.Phase.ShouldBe(UpdatePhase.Ready);
            window.GetVisualDescendants().OfType<TextBlock>().Any(t => t.Text == "Update ready. Waiting for dictation to finish.").ShouldBeTrue();
            UiCapture.Save(window, "compact-update-waiting.png");
        }
        finally { window.Close(); }
    }

    [AvaloniaFact]
    public async Task Failed_background_check_shows_retry_in_settings_controls()
    {
        var source = new Source { Fail = true };
        await using var updates = new UpdateService(source, new Installer(), new Version(1, 0, 0), "unused", "unused", () => false);
        var window = new Window { Width = 500, Content = new UpdateView(updates) }; window.Show();
        try
        {
            await Task.Run(updates.CheckAsync);
            Dispatcher.UIThread.RunJobs(); window.UpdateLayout();
            window.GetVisualDescendants().OfType<TextBlock>().Any(t => t.Text!.Contains("Could not check", StringComparison.Ordinal)).ShouldBeTrue();
            window.GetVisualDescendants().OfType<Button>().Single(b => Equals(b.Content, "Check for updates")).IsEnabled.ShouldBeTrue();
            source.Fail = false; await updates.CheckAsync();
            Dispatcher.UIThread.RunJobs(); window.UpdateLayout();
            updates.Snapshot.Phase.ShouldBe(UpdatePhase.Available);
        }
        finally { window.Close(); }
    }
    private sealed class Source : IUpdateSource
    {
        public bool Fail { get; set; }
        public int Downloads { get; private set; }
        public Task<UpdatePackage?> FindAsync(Version currentVersion, CancellationToken cancellationToken) => Fail
            ? Task.FromException<UpdatePackage?>(new HttpRequestException("offline"))
            : Task.FromResult<UpdatePackage?>(new(new Version(1, 0, 1), new Uri("https://example.invalid/update"), new Uri("https://example.invalid/checksum"), 1));
        public Task<string> DownloadAsync(UpdatePackage package, string directory, CancellationToken cancellationToken)
        { Downloads++; return Task.FromResult("unused.exe"); }
    }
    private sealed class Installer : IUpdateInstaller
    {
        public bool IsInstallationInProgress(string installationDirectory) => false;
        public Task<int> RunAsync(string installer, string installationDirectory, CancellationToken cancellationToken) => throw new InvalidOperationException("UI must not install before the engine is reserved.");
    }
}
