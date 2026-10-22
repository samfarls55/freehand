using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Interactivity;
using Avalonia.Styling;
using Avalonia.Themes.Fluent;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Freehand.App.Design;
using Freehand.App.Views;
using Freehand.Core;
using Freehand.Dictionary;
using Shouldly;
using Xunit;

[assembly: AvaloniaTestApplication(typeof(Freehand.AppTests.TestAppBuilder))]
namespace Freehand.AppTests;

public static class TestAppBuilder
{
    public static AppBuilder BuildAvaloniaApp() => AppBuilder.Configure<TestApp>().UseSkia()
        .UseHeadless(new AvaloniaHeadlessPlatformOptions { UseHeadlessDrawing = false });
}
public sealed class TestApp : Application
{
    public override void Initialize()
    {
        RequestedThemeVariant = ThemeVariant.Dark;
        Styles.Add(new FluentTheme()); Styles.Add(new CompactTheme());
    }
}

public sealed class MainWindowTests
{
    [AvaloniaFact]
    public async Task Background_transcript_save_reaches_text_delivery()
    {
        using var data = new UiData();
        var view = new TranscriptionsView(data.Store);
        var window = new Window { Content = view }; window.Show();
        try
        {
            var reachedDelivery = false;
            await Task.Run(() => { data.Store.Add(new TranscriptRecord { Text = "Speech reaches the cursor." }); reachedDelivery = true; });
            reachedDelivery.ShouldBeTrue(); Dispatcher.UIThread.RunJobs(); window.UpdateLayout();
            view.GetVisualDescendants().OfType<SelectableTextBlock>().Any(b => b.Text == "Speech reaches the cursor.").ShouldBeTrue();
        }
        finally { window.Close(); }
    }

    [AvaloniaFact]
    public void Tabs_preserve_search_and_refresh_hidden_history()
    {
        using var data = new UiData();
        var window = data.Window(); window.Show();
        try
        {
            var search = window.GetVisualDescendants().OfType<TextBox>().Single(t => Equals(t.Watermark, "Search history"));
            search.Text = "cursor";
            window.ShowSection("Dictionary");
            data.Store.Add(new TranscriptRecord { Text = "Text at the cursor." });
            window.ShowSection("History"); window.UpdateLayout();
            window.GetVisualDescendants().OfType<TextBox>().Single(t => Equals(t.Watermark, "Search history")).ShouldBeSameAs(search);
            search.Text.ShouldBe("cursor");
            window.GetVisualDescendants().OfType<SelectableTextBlock>().Single().Text.ShouldBe("Text at the cursor.");
            search.Text = "nothing matches"; Dispatcher.UIThread.RunJobs(); window.UpdateLayout();
            window.GetVisualDescendants().OfType<SelectableTextBlock>().ShouldBeEmpty();
        }
        finally { window.Close(); }
    }

    [AvaloniaFact]
    public void Settings_controls_persist_and_retain_the_existing_key_default()
    {
        using var data = new UiData();
        var window = data.Window(); window.Show(); window.ShowSection("Settings"); window.UpdateLayout();
        try
        {
            data.Settings.Data.PushToTalkKey.ShouldBe(0xA3);
            var view = window.GetVisualDescendants().OfType<SettingsView>().Single();
            var toggles = view.GetVisualDescendants().OfType<ToggleSwitch>().ToArray();
            toggles[0].IsChecked = false; toggles[1].IsChecked = false;
            var key = view.GetVisualDescendants().OfType<ComboBox>().Single(); key.SelectedIndex = 1;
            var persisted = new AppSettings(data.SettingsPath);
            persisted.Data.InjectText.ShouldBeFalse(); persisted.Data.KeepHistory.ShouldBeFalse();
            persisted.Data.PushToTalkKey.ShouldBe(0xA1);
            data.Settings.Update(data.Settings.Data with { PushToTalkKey = 0xA3, KeepHistory = true });
            key.SelectedIndex.ShouldBe(0); toggles[1].IsChecked.ShouldBe(true);
        }
        finally { window.Close(); }
    }

    [AvaloniaFact]
    public void Settings_model_details_follow_the_bundled_resolver_and_custom_selection()
    {
        using var data = new UiData();
        using var resolver = new Freehand.Speech.ModelResolver(cacheDirectory: Path.Combine(Path.GetTempPath(), "freehand-model-ui-" + Guid.NewGuid().ToString("N")));
        var window = data.Window(); window.Show(); window.ShowSection("Settings"); window.UpdateLayout();
        try
        {
            var details = window.GetVisualDescendants().OfType<Expander>().Single();
            details.IsExpanded = true; window.UpdateLayout();
            var modelPath = window.GetVisualDescendants().OfType<TextBlock>()
                .Single(b => b.Text?.StartsWith(resolver.BundledDirectory, StringComparison.Ordinal) == true);
            var custom = Path.Combine(Path.GetTempPath(), "freehand-custom-model");
            data.Settings.Update(data.Settings.Data with { ModelDirectory = custom });
            modelPath.Text.ShouldNotBeNull(); modelPath.Text.StartsWith(custom, StringComparison.Ordinal).ShouldBeTrue();
        }
        finally { window.Close(); }
    }

    [AvaloniaFact]
    public void Dictionary_editor_saves_a_literal_correction_and_preserves_disabled_state()
    {
        var original = new DictionaryEntry { Kind = EntryKind.Correction, Hear = "cloud code", Write = "Claude Code", IsEnabled = false };
        var editor = new DictionaryEditorWindow(original); DictionaryEntry? saved = null;
        editor.Saved += (_, value) => saved = value; editor.Show();
        try
        {
            var fields = editor.GetVisualDescendants().OfType<TextBox>().ToArray();
            fields[0].Text = "  a.b  "; fields[1].Text = "  $1  ";
            editor.GetVisualDescendants().OfType<Button>().Single(b => Equals(b.Content, "Save entry"))
                .RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            saved.ShouldNotBeNull(); saved.Id.ShouldBe(original.Id); saved.IsEnabled.ShouldBeFalse();
            saved.Kind.ShouldBe(EntryKind.Correction); saved.Hear.ShouldBe("a.b"); saved.Write.ShouldBe("$1");
        }
        finally { editor.Close(); }
    }

    [AvaloniaTheory]
    [InlineData(880, 700)]
    [InlineData(720, 520)]
    public void Compact_screens_render_at_normal_and_minimum_window_sizes(int width, int height)
    {
        using var data = new UiData(); data.Seed();
        var window = data.Window(); window.Width = width; window.Height = height; window.Show();
        try
        {
            foreach (var section in new[] { "History", "Dictionary", "Settings" })
            {
                window.ShowSection(section); window.UpdateLayout();
                window.Bounds.Width.ShouldBe(width); window.Bounds.Height.ShouldBe(height);
                var view = window.GetVisualDescendants().OfType<UserControl>().First();
                view.Bounds.Width.ShouldBeGreaterThan(0); view.Bounds.Height.ShouldBeGreaterThan(0);
                UiCapture.Save(window, $"compact-{section.ToLowerInvariant()}-{width}.png");
            }
            window.ToggleRecording(); window.IsRecording.ShouldBeTrue(); window.RecordLamp.IsLit.ShouldBeTrue();
            window.UpdateLayout(); UiCapture.Save(window, $"compact-recording-{width}.png");
            window.ToggleRecording(); window.IsRecording.ShouldBeFalse(); window.RecordLamp.IsLit.ShouldBeFalse();
            window.MinWidth.ShouldBe(720); window.MinHeight.ShouldBe(520);
        }
        finally { window.Close(); }
    }

    [AvaloniaFact]
    public void Recovery_actions_and_unsaved_transcript_remain_available()
    {
        using var data = new UiData(); data.Seed();
        var window = data.Window(); window.Show();
        try
        {
            window.ApplyFeedback(DictationState.AwaitingRetry, 0, null,
                new DictationFeedback(DictationOutcome.ModelFailure, "Recording kept. Retry or discard it.", Guid.NewGuid()));
            window.UpdateLayout();
            window.GetVisualDescendants().OfType<Button>().Single(b => Equals(b.Content, "Retry")).IsVisible.ShouldBeTrue();
            window.GetVisualDescendants().OfType<Button>().Single(b => Equals(b.Content, "Discard")).IsVisible.ShouldBeTrue();
            UiCapture.Save(window, "compact-recovery-880.png");
            var result = new DictationResult(DateTimeOffset.Now, TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(0.4), "Keep this transcript available.", []);
            window.ApplyFeedback(DictationState.Idle, 0, result,
                new DictationFeedback(DictationOutcome.DeliveryFailure, "Text insertion failed. Copy your transcript.", Guid.NewGuid()));
            window.UpdateLayout();
            window.GetVisualDescendants().OfType<TextBox>().Single(t => t.IsReadOnly).IsVisible.ShouldBeTrue();
            UiCapture.Save(window, "compact-delivery-failure-880.png");
            data.Settings.Update(data.Settings.Data with { KeepHistory = false });
            window.ApplyFeedback(DictationState.Idle, 0, result, new DictationFeedback(DictationOutcome.Success, "Transcript ready.", Guid.NewGuid()));
            window.GetVisualDescendants().OfType<TextBox>().Single(t => t.IsReadOnly).Text.ShouldBe(result.Text);
            window.GetVisualDescendants().OfType<TextBox>().Single(t => t.IsReadOnly).IsVisible.ShouldBeTrue();
            var editor = new DictionaryEditorWindow(null); editor.Show();
            try { UiCapture.Save(editor, "compact-dictionary-editor.png"); }
            finally { editor.Close(); }
        }
        finally { window.Close(); }
    }
}

internal static class UiCapture
{
    internal static void Save(Window window, string name)
    {
        AvaloniaHeadlessPlatform.ForceRenderTimerTick();
        using var frame = window.CaptureRenderedFrame(); frame.ShouldNotBeNull();
        if (Environment.GetEnvironmentVariable("FREEHAND_UI_CAPTURE_DIRECTORY") is { Length: > 0 } directory)
        {
            Directory.CreateDirectory(directory); frame.Save(Path.Combine(directory, name));
        }
    }
}

internal sealed class UiData : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "freehand-ui-" + Guid.NewGuid().ToString("N"));
    internal string SettingsPath => Path.Combine(_root, "settings.json");
    internal TranscriptStore Store { get; }
    internal DictionaryFile Dictionary { get; }
    internal AppSettings Settings { get; }
    internal UiData()
    {
        Directory.CreateDirectory(_root); Store = new TranscriptStore(Path.Combine(_root, "history.jsonl"));
        Dictionary = new DictionaryFile(Path.Combine(_root, "dictionary.txt")); Settings = new AppSettings(SettingsPath);
    }
    internal MainWindow Window() => new(null, Store, Dictionary, Settings);
    internal void Seed()
    {
        Store.Add(new TranscriptRecord { At = DateTimeOffset.Now.AddMinutes(-38), Text = "Let's keep the first version focused. History, dictionary, and settings are the only screens we need right now." });
        Store.Add(new TranscriptRecord { At = DateTimeOffset.Now.AddMinutes(-14), Text = "The keyboard shortcut should work wherever I'm writing, without bringing Freehand to the front." });
        Store.Add(new TranscriptRecord { At = DateTimeOffset.Now, Text = "Can you move our check-in to Thursday? I'd like a little more time to work through the prototype." });
        Dictionary.Add(new DictionaryEntry { Kind = EntryKind.Correction, Hear = "free hand", Write = "Freehand" });
        Dictionary.Add(new DictionaryEntry { Kind = EntryKind.Correction, Hear = "cloud code", Write = "Claude Code" });
        Dictionary.Add(new DictionaryEntry { Kind = EntryKind.Term, Write = "Parakeet" });
    }
    public void Dispose() => Directory.Delete(_root, true);
}
