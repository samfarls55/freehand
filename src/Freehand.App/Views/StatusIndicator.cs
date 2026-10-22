using Avalonia;
using Avalonia.Automation;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform;
using Avalonia.Threading;
using Freehand.Abstractions;
using Freehand.App.Controls;
using Freehand.App.Design;
using Freehand.Core;

namespace Freehand.App.Views;

internal sealed class StatusIndicator : Window
{
    private readonly IDesktopIntegration? _desktop;
    private readonly TextBlock _text;
    private readonly Lamp _lamp;
    private readonly DictationActivity _activity = new();
    private readonly DispatcherTimer _attentionTimer = new() { Interval = Tokens.Motion.StatusAttention };
    private readonly DispatcherTimer _activityTimer = new() { Interval = Tokens.Motion.StatusActivity };
    private Screen? _screen;
    private DictationState _state;
    private DictationFeedback? _attention;

    internal StatusIndicator(IDesktopIntegration? desktop = null)
    {
        _desktop = desktop;
        if (desktop is not null) Win32Properties.AddWindowStylesCallback(this, desktop.GetNonActivatingStyles);
        Title = "Freehand dictation";
        Width = Tokens.Size.StatusWidth;
        Height = Tokens.Size.StatusHeight;
        CanResize = false;
        ShowInTaskbar = false;
        ShowActivated = false;
        Focusable = false;
        Topmost = true;
        SystemDecorations = SystemDecorations.None;
        WindowStartupLocation = WindowStartupLocation.Manual;
        Background = Brushes.Transparent;
        TransparencyLevelHint = [WindowTransparencyLevel.Transparent];
        TransparencyBackgroundFallback = Tokens.Brushes.Deck;
        _text = new TextBlock
        {
            FontFamily = Tokens.Fonts.Grotesque,
            FontSize = Tokens.Fonts.Label,
            Foreground = Tokens.Brushes.InkOnDeck,
            VerticalAlignment = VerticalAlignment.Center,
        };
        _lamp = new Lamp { IsLit = true, VerticalAlignment = VerticalAlignment.Center };
        var row = new Grid
        {
            ColumnDefinitions = new ColumnDefinitions("Auto,*,Auto"),
            Margin = new Thickness(Tokens.Space.Roomy, Tokens.Space.Snug),
            ColumnSpacing = Tokens.Space.Snug,
            Children = { _lamp, _text, _activity },
        };
        Grid.SetColumn(_text, 1);
        Grid.SetColumn(_activity, 2);
        Content = new Border
        {
            Background = Tokens.Brushes.Deck,
            BorderBrush = Tokens.Brushes.Seam,
            BorderThickness = new Thickness(Tokens.Border.Hairline),
            CornerRadius = new CornerRadius(Tokens.Radius.Status),
            Child = row,
        };
        _attentionTimer.Tick += (_, _) => { _attentionTimer.Stop(); Hide(); };
        _activityTimer.Tick += (_, _) => _activity.Advance();
        Opened += (_, _) => PositionOnScreen();
        PropertyChanged += (_, e) =>
        {
            if (e.Property == IsVisibleProperty)
            {
                if (IsVisible && IsProcessing) _activityTimer.Start();
                else _activityTimer.Stop();
            }
        };
        Screens.Changed += OnScreensChanged;
        Closed += (_, _) =>
        {
            _attentionTimer.Stop();
            _activityTimer.Stop();
            Screens.Changed -= OnScreensChanged;
        };
    }

    private bool IsProcessing => _state is DictationState.Preparing or DictationState.Transcribing
        or DictationState.Recovering or DictationState.Delivering;

    internal void Update(bool mainHidden, DictationState state, float level = 0, DictationFeedback? feedback = null)
    {
        var starting = state == DictationState.Recording && _state != state;
        _state = state;
        var needsAttention = feedback?.Outcome is DictationOutcome.CaptureFailure
            or DictationOutcome.DeliveryFailure or DictationOutcome.EmptySpeech;
        var active = state == DictationState.Recording || IsProcessing;
        if (!active && (!mainHidden || state == DictationState.Stopping || (state == DictationState.Idle && !needsAttention)))
        {
            _attentionTimer.Stop();
            Hide();
            return;
        }
        if (state == DictationState.Idle)
        {
            // Level/model notifications must not extend or redisplay the same notice.
            if (ReferenceEquals(_attention, feedback) && !_attentionTimer.IsEnabled) { Hide(); return; }
            if (!ReferenceEquals(_attention, feedback)) { _attention = feedback; _attentionTimer.Start(); }
        }
        else
        {
            _attentionTimer.Stop();
            _attention = null;
        }
        Width = active ? Tokens.Size.StatusWidth : Tokens.Size.StatusAttentionWidth;
        _lamp.LampColor = state == DictationState.Recording ? Tokens.Colors.Record
            : active ? Tokens.Colors.Accent : Tokens.Colors.MeterAmber;
        _text.Text = state switch
        {
            DictationState.Recording => "Recording",
            DictationState.Recovering => "Recovering",
            DictationState.AwaitingRetry => "Retry or discard in Freehand",
            DictationState.Delivering => "Inserting",
            DictationState.Idle when feedback?.Outcome == DictationOutcome.EmptySpeech => "No audio. Check microphone",
            DictationState.Idle when feedback?.Outcome == DictationOutcome.DeliveryFailure => "Copy transcript in Freehand",
            DictationState.Idle => "Check microphone in Freehand",
            _ => "Processing",
        };
        AutomationProperties.SetName(this, "Freehand: " + _text.Text);
        _activity.Update(state, level);
        _activity.IsVisible = active;
        if (_screen is null || starting) SelectScreen();
        PositionOnScreen();
        if (!IsVisible) Show();
        if (IsProcessing) _activityTimer.Start();
        else _activityTimer.Stop();
    }

    private void SelectScreen()
    {
        var pointer = _desktop?.GetPointerPosition();
        _screen = pointer is { } point ? Screens.ScreenFromPoint(new PixelPoint(point.X, point.Y)) : null;
        _screen ??= Screens.Primary;
    }

    private void OnScreensChanged(object? sender, EventArgs e)
    {
        // Keep the session on its display when the pointer moves; recover if that display disappears.
        if (_screen is null || !Screens.All.Contains(_screen)) SelectScreen();
        if (IsVisible) PositionOnScreen();
    }

    private void PositionOnScreen()
    {
        if (_screen is { } screen) Position = CalculatePosition(screen.WorkingArea, screen.Scaling, Width);
    }

    internal static PixelPoint CalculatePosition(PixelRect area, double scaling, double width)
    {
        var pixelWidth = (int)Math.Round(width * scaling);
        var pixelHeight = (int)Math.Round(Tokens.Size.StatusHeight * scaling);
        var gap = (int)Math.Round(Tokens.Space.Roomy * scaling);
        return new PixelPoint(area.X + Math.Max(0, (area.Width - pixelWidth) / 2),
            Math.Max(area.Y, area.Bottom - pixelHeight - gap));
    }
}
