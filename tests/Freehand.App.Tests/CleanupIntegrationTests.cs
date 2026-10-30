using Avalonia.Automation;
using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.Interactivity;
using Avalonia.Input.Platform;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Freehand.Abstractions;
using Freehand.App;
using Freehand.App.Views;
using Freehand.Core;
using Shouldly;
using Xunit;

namespace Freehand.AppTests;

public sealed class CleanupIntegrationTests
{
    [AvaloniaTheory]
    [InlineData(null, false)]
    [InlineData("", false)]
    [InlineData("   ", false)]
    [InlineData("Send it Friday.", false)]
    [InlineData("um send it Thursday sorry Friday", true)]
    public void History_offers_original_recovery_only_for_a_distinct_saved_original(string? original, bool expected)
    {
        using var data = new UiData();
        data.Store.Add(new TranscriptRecord { Text = "Send it Friday.", OriginalText = original });
        var view = new TranscriptionsView(data.Store);
        var window = new Window { Content = view }; window.Show(); window.UpdateLayout();
        try
        {
            view.GetVisualDescendants().OfType<Button>().Count(button => Equals(button.Content, "Copy original")).ShouldBe(expected ? 1 : 0);
            view.GetVisualDescendants().OfType<Button>().Count(button => Equals(button.Content, "Copy")).ShouldBe(1);
        }
        finally { window.Close(); }
    }

    [AvaloniaFact]
    public async Task History_copy_actions_select_final_and_original_text_independently()
    {
        using var data = new UiData();
        const string original = "um send it Thursday sorry Friday";
        const string final = "Send it Friday.";
        data.Store.Add(new TranscriptRecord { Text = final, OriginalText = original });
        var view = new TranscriptionsView(data.Store);
        var window = new Window { Content = view }; window.Show(); window.UpdateLayout();
        try
        {
            var clipboard = window.Clipboard;
            clipboard.ShouldNotBeNull();
            view.GetVisualDescendants().OfType<Button>().Single(button => Equals(button.Content, "Copy original"))
                .RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            await Task.Yield(); Dispatcher.UIThread.RunJobs();
            (await clipboard.TryGetTextAsync()).ShouldBe(original);
            view.GetVisualDescendants().OfType<Button>().Single(button => Equals(button.Content, "Copy"))
                .RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            await Task.Yield(); Dispatcher.UIThread.RunJobs();
            (await clipboard.TryGetTextAsync()).ShouldBe(final);
        }
        finally { window.Close(); }
    }

    [AvaloniaFact]
    public void Cleanup_toggle_persists_and_missing_assets_have_an_explicit_status()
    {
        using var data = new UiData();
        data.Settings.TryUpdate(data.Settings.Data with { CleanupDirectory = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N")) }).ShouldBeTrue();
        var view = new SettingsView(data.Settings);
        var window = new Window { Content = view }; window.Show(); window.UpdateLayout();
        try
        {
            var toggle = view.GetVisualDescendants().OfType<ToggleSwitch>()
                .Single(control => AutomationProperties.GetName(control) == "Clean up dictated text");
            toggle.IsChecked.ShouldBe(true);
            view.GetVisualDescendants().OfType<TextBlock>().Any(text => text.Text == "No cleanup model installed").ShouldBeTrue();
            toggle.IsChecked = false;
            new AppSettings(data.SettingsPath).Data.CleanupEnabled.ShouldBeFalse();
            view.GetVisualDescendants().OfType<TextBlock>().Any(text => text.Text == "Off").ShouldBeTrue();
            data.Settings.TryUpdate(data.Settings.Data with { CleanupEnabled = true }).ShouldBeTrue();
            toggle.IsChecked.ShouldBe(true);
        }
        finally { window.Close(); }
    }

    [AvaloniaFact]
    public void Cleanup_stays_visible_and_blocks_a_second_recording_in_the_window()
    {
        using var data = new UiData();
        var window = data.Window(); window.Show();
        var indicator = new StatusIndicator();
        try
        {
            window.ApplyFeedback(DictationState.Cleaning, 0, null, null);
            window.UpdateLayout();
            var record = window.GetVisualDescendants().OfType<Button>()
                .Single(button => button.GetVisualDescendants().OfType<TextBlock>().Any(text => text.Text == "Cleaning up"));
            record.IsEnabled.ShouldBeFalse();
            indicator.Update(false, DictationState.Cleaning);
            indicator.IsVisible.ShouldBeTrue();
            indicator.GetVisualDescendants().OfType<TextBlock>().Single().Text.ShouldBe("Cleaning up");
            indicator.ShowActivated.ShouldBeFalse();
            indicator.Focusable.ShouldBeFalse();
            indicator.Update(false, DictationState.Idle);
            indicator.IsVisible.ShouldBeFalse();
        }
        finally { indicator.Close(); window.Close(); }
    }

    [Fact]
    public async Task Model_selection_is_lazy_and_disabling_disposes_the_owned_processor()
    {
        using var assets = new CleanupAssets("first-model");
        var created = new List<RecordingProcessor>();
        await using var configured = new ConfiguredTranscriptPostProcessor(assets.DirectoryPath, new UnusedLauncher(), (_, _) =>
        {
            var processor = new RecordingProcessor(); created.Add(processor); return processor;
        });
        configured.IsAvailable.ShouldBeTrue();
        configured.ModelId.ShouldBe("first-model");
        created.ShouldBeEmpty("parsing settings must not create or load a model worker");
        (await configured.ProcessAsync("um send it Friday", CancellationToken.None)).ShouldBe("send it Friday");
        (await configured.ProcessAsync("um keep my wording", CancellationToken.None)).ShouldBe("keep my wording");
        created.Count.ShouldBe(1);
        created[0].Calls.ShouldBe(2);
        await configured.ConfigureAsync(assets.DirectoryPath, enabled: false);
        created[0].Disposed.ShouldBeTrue();
        configured.Status(false).ShouldBe("Off");
        await configured.ConfigureAsync(assets.DirectoryPath, enabled: true);
        await configured.ProcessAsync("um try again", CancellationToken.None);
        created.Count.ShouldBe(2);
    }

    [Fact]
    public async Task Changing_model_folder_releases_the_previous_processor_and_uses_the_new_selection()
    {
        using var first = new CleanupAssets("first-model");
        using var second = new CleanupAssets("second-model");
        var created = new List<RecordingProcessor>();
        await using var configured = new ConfiguredTranscriptPostProcessor(first.DirectoryPath, new UnusedLauncher(), (_, _) =>
        {
            var processor = new RecordingProcessor(); created.Add(processor); return processor;
        });
        await configured.ProcessAsync("um first", CancellationToken.None);
        await configured.ConfigureAsync(second.DirectoryPath, enabled: true);
        created[0].Disposed.ShouldBeTrue();
        configured.ModelId.ShouldBe("second-model");
        await configured.ProcessAsync("um second", CancellationToken.None);
        created.Count.ShouldBe(2);
    }

    [Fact]
    public async Task Late_completion_from_a_replaced_processor_cannot_mark_the_new_model_ready()
    {
        using var first = new CleanupAssets("first-model");
        using var second = new CleanupAssets("second-model");
        var oldProcessor = new DelayedProcessor();
        await using var configured = new ConfiguredTranscriptPostProcessor(first.DirectoryPath, new UnusedLauncher(), (_, _) => oldProcessor);
        var pending = configured.ProcessAsync("earlier transcript", CancellationToken.None).AsTask();
        configured.Status(true).ShouldBe("Cleaning up");
        await configured.ConfigureAsync(second.DirectoryPath, enabled: true);
        oldProcessor.Disposed.ShouldBeTrue();
        oldProcessor.Completion.SetResult("late earlier text");
        await pending;
        configured.ModelId.ShouldBe("second-model");
        configured.Status(true).ShouldBe("Installed · verifies and loads when you dictate");
    }

    [Theory]
    [InlineData(null, "No cleanup model installed")]
    [InlineData("{invalid", "Cleanup model needs installation or repair")]
    [InlineData("{}", "Cleanup model needs installation or repair")]
    [InlineData("[]", "Cleanup model needs installation or repair")]
    [InlineData("{\"promptStyle\":\"unsupported\"}", "Cleanup model needs installation or repair")]
    public async Task Missing_or_invalid_assets_do_not_start_a_worker_and_can_be_reloaded_after_repair(string? invalidManifest, string expectedStatus)
    {
        using var assets = new CleanupAssets("repaired-model");
        var manifest = Path.Combine(assets.DirectoryPath, "cleanup-manifest.json");
        var original = File.ReadAllText(manifest);
        if (invalidManifest is null) File.Delete(manifest);
        else File.WriteAllText(manifest, invalidManifest);
        var creations = 0;
        await using var configured = new ConfiguredTranscriptPostProcessor(assets.DirectoryPath, new UnusedLauncher(), (_, _) =>
        {
            creations++; return new RecordingProcessor();
        });
        configured.IsAvailable.ShouldBeFalse();
        configured.Status(true).ShouldBe(expectedStatus);
        await Should.ThrowAsync<InvalidOperationException>(async () => await configured.ProcessAsync("private words", CancellationToken.None));
        creations.ShouldBe(0);
        File.WriteAllText(manifest, original);
        await configured.ConfigureAsync(assets.DirectoryPath, enabled: true, reload: true);
        configured.IsAvailable.ShouldBeTrue();
        await configured.ProcessAsync("um repaired", CancellationToken.None);
        creations.ShouldBe(1);
    }

    [Fact]
    public async Task Unavailable_platform_cannot_claim_cleanup_is_ready()
    {
        using var assets = new CleanupAssets("local-model");
        await using var configured = new ConfiguredTranscriptPostProcessor(assets.DirectoryPath, null);
        configured.IsAvailable.ShouldBeFalse();
        configured.Status(true).ShouldBe("Cleanup worker unavailable");
    }

    private sealed class UnusedLauncher : ICleanupWorkerLauncher
    {
        public IWorkerProcess Launch(CleanupWorkerStartInfo startInfo) => throw new InvalidOperationException("A fake processor should not launch a worker.");
    }

    private sealed class RecordingProcessor : ITranscriptPostProcessor
    {
        internal int Calls { get; private set; }
        internal bool Disposed { get; private set; }
        public ValueTask<string> ProcessAsync(string text, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Calls++;
            return ValueTask.FromResult(text.Replace("um ", "", StringComparison.Ordinal));
        }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }

    private sealed class DelayedProcessor : ITranscriptPostProcessor
    {
        internal TaskCompletionSource<string> Completion { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal bool Disposed { get; private set; }
        public ValueTask<string> ProcessAsync(string text, CancellationToken cancellationToken) => new(Completion.Task);
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }

    private sealed class CleanupAssets : IDisposable
    {
        internal string DirectoryPath { get; } = Path.Combine(Path.GetTempPath(), "freehand-cleanup-composition-" + Guid.NewGuid().ToString("N"));
        internal CleanupAssets(string modelId)
        {
            Directory.CreateDirectory(DirectoryPath);
            File.WriteAllText(Path.Combine(DirectoryPath, "runtime.exe"), "fake-runtime");
            File.WriteAllText(Path.Combine(DirectoryPath, "model.gguf"), "fake-model");
            var hash = new string('0', 64);
            File.WriteAllText(Path.Combine(DirectoryPath, "cleanup-manifest.json"), $$"""
                {"modelId":"{{modelId}}","runtimePath":"runtime.exe","runtimeSha256":"{{hash}}",
                 "modelPath":"model.gguf","modelSha256":"{{hash}}","promptStyle":"QuillChatMl"}
                """);
        }
        public void Dispose() { if (Directory.Exists(DirectoryPath)) Directory.Delete(DirectoryPath, true); }
    }
}
