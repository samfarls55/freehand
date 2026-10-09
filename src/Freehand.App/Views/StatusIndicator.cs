using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using Freehand.App.Controls;
using Freehand.App.Design;
using Freehand.Core;

namespace Freehand.App.Views;

internal sealed class StatusIndicator : Window
{
    private readonly Composition _composition;
    private readonly TextBlock _text;
    private readonly Lamp _lamp;
    private bool _configured;
    private DictationFeedback? _attention;
    private readonly DispatcherTimer _attentionTimer = new() { Interval = TimeSpan.FromSeconds(3) };
    internal StatusIndicator(Composition composition)
    {
        _composition = composition;
        _attentionTimer.Tick += (_, _) => { _attentionTimer.Stop(); Hide(); };
        Closed += (_, _) => _attentionTimer.Stop();
        Title = "Freehand status"; Width = Tokens.Size.StatusWidth; Height = Tokens.Size.StatusHeight; CanResize = false;
        ShowInTaskbar = false; ShowActivated = false; Topmost = true;
        SystemDecorations = SystemDecorations.None; Background = Tokens.Brushes.Chassis;
        _text = new TextBlock { FontFamily = Tokens.Fonts.Grotesque, FontSize = Tokens.Fonts.Label, Foreground = Tokens.Brushes.Ink, VerticalAlignment = VerticalAlignment.Center };
        _lamp = new Lamp { IsLit = true, LampColor = Tokens.Colors.Record };
        Content = new BrushedPanel { Child = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(Tokens.Space.Base), Spacing = Tokens.Space.Base, Children = { _lamp, _text } } };
        Opened += (_, _) =>
        {
            if (!_configured)
            {
                var handle = TryGetPlatformHandle();
                if (handle is not null) _composition.Desktop?.MakeNonActivating(handle.Handle);
                _configured = true;
            }
            var area = Screens.Primary?.WorkingArea;
            if (area is not null) Position = new PixelPoint(area.Value.Right - (int)(Width * DesktopScaling) - (int)Tokens.Space.Wide, area.Value.Bottom - (int)(Height * DesktopScaling) - (int)Tokens.Space.Wide);
        };
    }
    internal void Update(bool hidden, DictationState state)
    {
        var needsAttention = _composition.Engine?.Feedback?.Outcome is DictationOutcome.CaptureFailure or DictationOutcome.DeliveryFailure or DictationOutcome.EmptySpeech;
        if (!hidden || (state == DictationState.Idle && !needsAttention)) { _attentionTimer.Stop(); Hide(); return; }
        if (state == DictationState.Idle)
        {
            var feedback = _composition.Engine?.Feedback;
            if (ReferenceEquals(_attention, feedback) && !_attentionTimer.IsEnabled) { Hide(); return; }
            if (!ReferenceEquals(_attention, feedback)) { _attention = feedback; _attentionTimer.Start(); }
        }
        else _attentionTimer.Stop();
        _lamp.LampColor = state == DictationState.Recording ? Tokens.Colors.Record : Tokens.Colors.MeterAmber;
        _text.Text = state switch
        {
            DictationState.Recording => "Recording",
            DictationState.Preparing => "Preparing transcript",
            DictationState.Recovering => "Recovering recording",
            DictationState.AwaitingRetry => "Open Freehand to Retry or Discard",
            DictationState.Transcribing or DictationState.Delivering => "Finishing transcript",
            _ => "Open Freehand for details",
        };
        if (!IsVisible) Show();
    }
}
