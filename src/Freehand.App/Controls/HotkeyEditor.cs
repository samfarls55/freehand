using Avalonia;
using Avalonia.Automation;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using Freehand.Abstractions;
using Freehand.App.Design;
using Freehand.App.Views;

namespace Freehand.App.Controls;

/// <summary>A native shortcut recorder with an explicit cancel action so every key is bindable.</summary>
internal sealed class HotkeyEditor : StackPanel
{
    private readonly IHotkeyRecorder? _recorder;
    private readonly Action<IReadOnlyList<int>> _save;
    private readonly Button _record = Panels.Button("");
    private readonly Button _cancel = Panels.Button("Cancel", quiet: true);
    private readonly TextBlock _label = Panels.Text("", Tokens.Fonts.Control);
    private CancellationTokenSource? _capture;
    private IReadOnlyList<int> _keys = [0xA3];

    internal HotkeyEditor(IHotkeyRecorder? recorder, Action<IReadOnlyList<int>> save)
    {
        _recorder = recorder; _save = save;
        Orientation = Orientation.Vertical; Spacing = Tokens.Space.Snug;
        _label.TextWrapping = TextWrapping.Wrap; _label.MaxWidth = 180;
        _record.HorizontalAlignment = HorizontalAlignment.Right; _cancel.HorizontalAlignment = HorizontalAlignment.Right;
        _record.Content = _label; _record.MinWidth = 152; _cancel.IsVisible = false;
        _record.BorderBrush = Tokens.Brushes.Seam; _record.BorderThickness = new Thickness(Tokens.Border.Hairline);
        AutomationProperties.SetName(_record, "Change push-to-talk key");
        _record.IsEnabled = recorder is not null;
        _record.Click += async (_, _) => await RecordAsync();
        _cancel.Click += (_, _) => Cancel();
        Children.Add(_record); Children.Add(_cancel);
    }

    internal void Synchronize(IReadOnlyList<int> keys)
    {
        _keys = keys;
        if (_capture is null) _label.Text = HotkeyLabel.Format(keys);
    }

    internal void Cancel() => _capture?.Cancel();

    private async Task RecordAsync()
    {
        if (_capture is not null || _recorder is null) return;
        using var capture = new CancellationTokenSource(); _capture = capture;
        var owner = TopLevel.GetTopLevel(this) as Window;
        if (owner is not null)
        {
            owner.PropertyChanged += OwnerPropertyChanged;
            owner.AddHandler(InputElement.KeyDownEvent, CaptureKey, RoutingStrategies.Tunnel, handledEventsToo: true);
            owner.AddHandler(InputElement.KeyUpEvent, CaptureKey, RoutingStrategies.Tunnel, handledEventsToo: true);
        }
        _label.Text = "Press keys..."; _record.IsEnabled = false; _cancel.IsVisible = true;
        try
        {
            var progress = new Progress<IReadOnlyList<int>>(keys => Dispatcher.UIThread.Post(() =>
            {
                if (ReferenceEquals(_capture, capture) && !capture.IsCancellationRequested)
                    _label.Text = HotkeyLabel.Format(keys);
            }));
            var keys = await _recorder.RecordAsync(progress, capture.Token);
            if (!capture.IsCancellationRequested && keys is { Count: > 0 }) _save(keys);
            else if (!capture.IsCancellationRequested) _label.Text = "Finish dictation first";
        }
        catch (OperationCanceledException) { }
        finally
        {
            if (owner is not null)
            {
                owner.PropertyChanged -= OwnerPropertyChanged;
                owner.RemoveHandler(InputElement.KeyDownEvent, CaptureKey);
                owner.RemoveHandler(InputElement.KeyUpEvent, CaptureKey);
            }
            _capture = null; _record.IsEnabled = true; _cancel.IsVisible = false;
            if (_label.Text != "Finish dictation first" || capture.IsCancellationRequested)
                _label.Text = HotkeyLabel.Format(_keys);
        }
    }

    private void OwnerPropertyChanged(object? sender, AvaloniaPropertyChangedEventArgs e)
    {
        if (e.Property == IsVisibleProperty && e.NewValue is false) Cancel();
    }
    private static void CaptureKey(object? sender, KeyEventArgs e) => e.Handled = true;

    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
    {
        Cancel(); base.OnDetachedFromVisualTree(e);
    }
}
