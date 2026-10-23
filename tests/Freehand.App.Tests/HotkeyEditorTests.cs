using Avalonia.Automation;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Freehand.Abstractions;
using Freehand.App.Controls;
using Freehand.App.Views;
using Freehand.Core;
using Shouldly;
using Xunit;

namespace Freehand.AppTests;

public sealed class HotkeyEditorTests
{
    [AvaloniaFact]
    public void Choosing_a_custom_combination_persists_and_updates_both_settings_views()
    {
        using var data = new UiData();
        var recorder = new ImmediateRecorder([0xA2, 0xA1, 0x41]);
        var view = new SettingsView(data.Settings, null, recorder);
        var window = new Window { Content = view, Width = 540, Height = 700 }; window.Show();
        var other = new Window { Content = new SettingsView(data.Settings, null, recorder) }; other.Show();
        try
        {
            RecordButton(view).RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            var reopened = new AppSettings(data.SettingsPath);
            reopened.Data.DictationKeys.ShouldBe([0x41, 0xA1, 0xA2]);
            view.GetVisualDescendants().OfType<TextBlock>().Any(t => t.Text == "Left Ctrl + Right Shift + A").ShouldBeTrue();
            other.GetVisualDescendants().OfType<TextBlock>().Any(t => t.Text == "Left Ctrl + Right Shift + A").ShouldBeTrue();
            window.UpdateLayout(); UiCapture.Save(window, "custom-hotkey-settings-540.png");
        }
        finally { other.Close(); window.Close(); }
    }

    [AvaloniaTheory]
    [InlineData(0x03)]
    [InlineData(0x09)]
    [InlineData(0x1B)]
    [InlineData(0x41)]
    [InlineData(0xB3)]
    public void Keys_outside_the_old_presets_can_be_chosen(int key)
    {
        using var data = new UiData();
        var view = new SettingsView(data.Settings, null, new ImmediateRecorder([key]));
        var window = new Window { Content = view }; window.Show();
        try
        {
            RecordButton(view).RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            new AppSettings(data.SettingsPath).Data.DictationKeys.ShouldBe([key]);
        }
        finally { window.Close(); }
    }

    [AvaloniaFact]
    public void Long_combinations_wrap_and_survive_a_new_settings_session()
    {
        using var data = new UiData();
        data.Settings.Update(data.Settings.Data with { PushToTalkKeys = [0xA2, 0xA1, 0xA4, 0x5B, 0x41, 0x42] });
        var reopened = new AppSettings(data.SettingsPath);
        var view = new SettingsView(reopened, null, new ImmediateRecorder([]))
        { Margin = new Avalonia.Thickness(32, 0, 32, 16) };
        var window = new Window { Content = view, Width = 540, Height = 700 }; window.Show();
        try
        {
            window.UpdateLayout();
            var button = RecordButton(view);
            var label = button.GetVisualDescendants().OfType<TextBlock>().Single();
            label.Text.ShouldBe("Left Ctrl + Right Shift + Left Alt + Left Win + A + B");
            label.Bounds.Height.ShouldBeGreaterThan(20);
            button.Bounds.Width.ShouldBeLessThan(220);
            UiCapture.Save(window, "custom-hotkey-long-540.png");
        }
        finally { window.Close(); }
    }

    [AvaloniaFact]
    public async Task Recording_blocks_tab_navigation_and_cancel_preserves_the_saved_binding()
    {
        using var data = new UiData();
        var recorder = new PendingRecorder();
        var view = new SettingsView(data.Settings, null, recorder);
        var window = new Window { Content = view, Width = 540, Height = 700 }; window.Show();
        try
        {
            RecordButton(view).RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            recorder.Progress.ShouldNotBeNull();
            var toggle = view.GetVisualDescendants().OfType<ToggleSwitch>().First(); toggle.Focus();
            window.KeyPressQwerty(PhysicalKey.Tab, RawInputModifiers.None);
            window.KeyReleaseQwerty(PhysicalKey.Tab, RawInputModifiers.None);
            toggle.IsFocused.ShouldBeTrue();
            window.UpdateLayout(); UiCapture.Save(window, "custom-hotkey-recording-540.png");
            view.GetVisualDescendants().OfType<Button>().Single(b => Equals(b.Content, "Cancel"))
                .RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            await WaitUntilAsync(() => RecordButton(view).IsEnabled);
            new AppSettings(data.SettingsPath).Data.DictationKeys.ShouldBe([0xA3]);
            view.GetVisualDescendants().OfType<TextBlock>().Any(t => t.Text == "Right Ctrl").ShouldBeTrue();
        }
        finally { window.Close(); }
    }

    [AvaloniaFact]
    public async Task Closing_the_settings_window_cancels_recording()
    {
        using var data = new UiData(); var recorder = new PendingRecorder();
        var view = new SettingsView(data.Settings, null, recorder);
        var window = new Window { Content = view }; window.Show();
        RecordButton(view).RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        window.Close();
        await WaitUntilAsync(() => recorder.Token.IsCancellationRequested);
        data.Settings.Data.DictationKeys.ShouldBe([0xA3]);
    }

    private static Button RecordButton(Control view) => view.GetVisualDescendants().OfType<Button>()
        .Single(b => AutomationProperties.GetName(b) == "Change push-to-talk key");

    private static async Task WaitUntilAsync(Func<bool> condition)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        while (!condition()) { await Task.Delay(10, timeout.Token); Dispatcher.UIThread.RunJobs(); }
    }

    private sealed class ImmediateRecorder(int[] keys) : IHotkeyRecorder
    {
        public Task<IReadOnlyList<int>?> RecordAsync(IProgress<IReadOnlyList<int>> progress, CancellationToken cancellationToken) =>
            Task.FromResult<IReadOnlyList<int>?>(keys);
    }

    private sealed class PendingRecorder : IHotkeyRecorder
    {
        internal IProgress<IReadOnlyList<int>>? Progress { get; private set; }
        internal CancellationToken Token { get; private set; }
        public Task<IReadOnlyList<int>?> RecordAsync(IProgress<IReadOnlyList<int>> progress, CancellationToken cancellationToken)
        {
            Progress = progress; Token = cancellationToken;
            return new TaskCompletionSource<IReadOnlyList<int>?>(TaskCreationOptions.RunContinuationsAsynchronously).Task.WaitAsync(cancellationToken);
        }
    }
}
