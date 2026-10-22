using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Freehand.Abstractions;
using Freehand.App.Controls;
using Freehand.App.Design;
using Freehand.App.Views;
using Freehand.Core;
using Shouldly;
using Xunit;

namespace Freehand.AppTests;

public sealed class StatusIndicatorTests
{
    [AvaloniaTheory]
    [InlineData(false)]
    [InlineData(true)]
    public void Dictation_stays_visible_through_delivery_and_hides_on_completion(bool mainHidden)
    {
        var desktop = new IndicatorDesktop();
        var indicator = new StatusIndicator(desktop);
        try
        {
            indicator.Update(mainHidden, DictationState.Idle);
            indicator.IsVisible.ShouldBeFalse();
            foreach (var state in new[] { DictationState.Recording, DictationState.Preparing,
                DictationState.Transcribing, DictationState.Recovering, DictationState.Delivering })
            {
                indicator.Update(mainHidden, state, 0.06f);
                indicator.IsVisible.ShouldBeTrue($"{state} must be visible with the main window open or hidden");
                indicator.GetVisualDescendants().OfType<Lamp>().Single().LampColor
                    .ShouldBe(state == DictationState.Recording ? Tokens.Colors.Record : Tokens.Colors.Accent);
            }
            desktop.PointerReads.ShouldBe(1, "moving the pointer during processing must not relocate the bubble");
            indicator.ShowActivated.ShouldBeFalse();
            indicator.Focusable.ShouldBeFalse();
            indicator.ShowInTaskbar.ShouldBeFalse();
            indicator.Topmost.ShouldBeTrue();
            indicator.Update(mainHidden, DictationState.Idle);
            indicator.IsVisible.ShouldBeFalse();
            indicator.Update(mainHidden, DictationState.Recording);
            desktop.PointerReads.ShouldBe(2, "each new dictation chooses its display again");
            indicator.Update(mainHidden, DictationState.Stopping);
            indicator.IsVisible.ShouldBeFalse();
        }
        finally { indicator.Close(); }
    }

    [AvaloniaTheory]
    [InlineData(false)]
    [InlineData(true)]
    public void Retry_keeps_the_recording_display_when_main_window_hides_the_notice(bool restoreNoticeBeforeRetry)
    {
        var desktop = new IndicatorDesktop();
        var indicator = new StatusIndicator(desktop);
        try
        {
            indicator.Update(true, DictationState.Recording);
            indicator.Update(true, DictationState.AwaitingRetry);
            indicator.IsVisible.ShouldBeTrue();
            Status(indicator).ShouldBe("Retry or discard in Freehand");
            indicator.Update(false, DictationState.AwaitingRetry);
            indicator.IsVisible.ShouldBeFalse();
            desktop.PointerPosition = (1000, 600);
            if (restoreNoticeBeforeRetry)
            {
                indicator.Update(true, DictationState.AwaitingRetry);
                indicator.IsVisible.ShouldBeTrue();
            }
            indicator.Update(true, DictationState.Transcribing);
            Status(indicator).ShouldBe("Processing");
            desktop.PointerReads.ShouldBe(1, "retrying or restoring a notice must keep the recording's display");
            indicator.Update(true, DictationState.Idle);
            indicator.IsVisible.ShouldBeFalse();
            indicator.Update(true, DictationState.Recording);
            desktop.PointerReads.ShouldBe(2, "a new recording chooses its display from the current pointer");
        }
        finally { indicator.Close(); }
    }

    [AvaloniaTheory]
    [InlineData(DictationOutcome.CaptureFailure, "Check microphone in Freehand")]
    [InlineData(DictationOutcome.DeliveryFailure, "Copy transcript in Freehand")]
    [InlineData(DictationOutcome.EmptySpeech, "No audio. Check microphone")]
    public async Task Errors_expire_once_and_do_not_hide_a_new_recording(DictationOutcome outcome, string message)
    {
        var indicator = new StatusIndicator();
        var feedback = new DictationFeedback(outcome, "Details in the main window", Guid.NewGuid());
        try
        {
            indicator.Update(true, DictationState.Idle, feedback: feedback);
            indicator.IsVisible.ShouldBeTrue();
            Status(indicator).ShouldBe(message);
            await Task.Delay(Tokens.Motion.StatusAttention + TimeSpan.FromMilliseconds(150));
            Dispatcher.UIThread.RunJobs();
            indicator.IsVisible.ShouldBeFalse();
            indicator.Update(true, DictationState.Idle, feedback: feedback);
            indicator.IsVisible.ShouldBeFalse("the same outcome must not keep reappearing");
            indicator.Update(true, DictationState.Idle, feedback: feedback with { JobId = Guid.NewGuid() });
            indicator.IsVisible.ShouldBeTrue();
            indicator.Update(false, DictationState.Recording);
            await Task.Delay(Tokens.Motion.StatusAttention + TimeSpan.FromMilliseconds(150));
            Dispatcher.UIThread.RunJobs();
            indicator.IsVisible.ShouldBeTrue("an old error timer must not dismiss an active dictation");
            Status(indicator).ShouldBe("Recording");
        }
        finally { indicator.Close(); }
    }

    [AvaloniaTheory]
    [InlineData(0, 0, 1920, 1040, 1, 856, 980)]
    [InlineData(-2560, -200, 2560, 1400, 1.5, -1436, 1110)]
    [InlineData(1920, 48, 3840, 2112, 2, 3632, 2040)]
    public void Position_centers_in_the_work_area_with_scaled_taskbar_clearance(
        int x, int y, int width, int height, double scale, int expectedX, int expectedY)
    {
        var area = new PixelRect(x, y, width, height);
        StatusIndicator.CalculatePosition(area, scale, Tokens.Size.StatusWidth)
            .ShouldBe(new PixelPoint(expectedX, expectedY));
        var attention = StatusIndicator.CalculatePosition(area, scale, Tokens.Size.StatusAttentionWidth);
        (attention.X + (int)(Tokens.Size.StatusAttentionWidth * scale) / 2).ShouldBe(x + width / 2);
        attention.Y.ShouldBe(expectedY);
    }

    [AvaloniaTheory]
    [InlineData(false)]
    [InlineData(true)]
    public void Compact_layout_renders_without_clipping_with_either_system_theme(bool dark)
    {
        var previousTheme = Application.Current!.RequestedThemeVariant;
        Application.Current.RequestedThemeVariant = dark ? Avalonia.Styling.ThemeVariant.Dark : Avalonia.Styling.ThemeVariant.Light;
        var indicator = new StatusIndicator();
        try
        {
            foreach (var state in new[] { DictationState.Recording, DictationState.Transcribing, DictationState.AwaitingRetry })
            {
                foreach (var level in new[] { 0.01f, 0.06f, 0.12f, 0.02f, 0.005f }) indicator.Update(true, state, level);
                indicator.UpdateLayout();
                var text = indicator.GetVisualDescendants().OfType<TextBlock>().Single();
                text.Bounds.Width.ShouldBeGreaterThanOrEqualTo(text.DesiredSize.Width);
                text.Bounds.Height.ShouldBeGreaterThanOrEqualTo(text.DesiredSize.Height);
                indicator.Bounds.Height.ShouldBe(Tokens.Size.StatusHeight);
                var activity = indicator.GetVisualDescendants().OfType<DictationActivity>().Single();
                activity.IsVisible.ShouldBe(state != DictationState.AwaitingRetry);
                AvaloniaHeadlessPlatform.ForceRenderTimerTick();
                using var frame = indicator.CaptureRenderedFrame();
                frame.ShouldNotBeNull();
                if (Environment.GetEnvironmentVariable("FREEHAND_UI_CAPTURE_DIRECTORY") is { Length: > 0 } directory)
                {
                    Directory.CreateDirectory(directory);
                    frame.Save(Path.Combine(directory, $"dictation-{(dark ? "dark" : "light")}-{state}.png"));
                }
            }
        }
        finally { indicator.Close(); Application.Current.RequestedThemeVariant = previousTheme; }
    }

    private static string? Status(StatusIndicator indicator) => indicator.GetVisualDescendants().OfType<TextBlock>().Single().Text;

    private sealed class IndicatorDesktop : IDesktopIntegration
    {
        internal int PointerReads { get; private set; }
        internal (int X, int Y) PointerPosition { get; set; } = (100, 100);
        public (int X, int Y)? GetPointerPosition() { PointerReads++; return PointerPosition; }
        public (uint Style, uint ExtendedStyle) GetNonActivatingStyles(uint style, uint extendedStyle) => (style, extendedStyle);
        public ForegroundTarget Capture() => default;
        public bool IsCurrent(ForegroundTarget target) => true;
        public bool ClaimInstance() => true;
        public void RequestExistingShutdown() { }
        public void StartNotifications() { }
        public void SetLoginStartup(bool enabled) { }
        public void Open(string path) { }
        public void Dispose() { }
        public event EventHandler? ActivationRequested { add { } remove { } }
        public event EventHandler? ShutdownRequested { add { } remove { } }
        public event EventHandler? ReadinessInvalidated { add { } remove { } }
    }
}
