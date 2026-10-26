using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Threading;
using Freehand.App.Design;
using Freehand.Core.Updates;

namespace Freehand.App.Views;

/// <summary>Shared update controls for Settings and the non-activating prompt.</summary>
internal sealed class UpdateView : UserControl
{
    private readonly UpdateService? _updates;
    private readonly TextBlock _status = Panels.Text("");
    private readonly Button _check = Panels.Button("Check for updates", quiet: true);
    private readonly Button _update = Panels.Button("Update", primary: true);
    private readonly Button? _later;

    internal UpdateView(UpdateService? updates, Action? defer = null)
    {
        _updates = updates;
        _check.Click += async (_, _) => { if (_updates is not null) await _updates.CheckAsync().ConfigureAwait(true); };
        _update.Click += async (_, _) => { if (_updates is not null) await _updates.DownloadAsync().ConfigureAwait(true); };
        var actions = new WrapPanel { ItemSpacing = Tokens.Space.Snug, LineSpacing = Tokens.Space.Snug, Children = { _update, _check } };
        _check.IsVisible = defer is null;
        if (defer is not null)
        {
            _later = Panels.Button("Later", quiet: true); _later.Click += (_, _) => defer(); actions.Children.Add(_later);
        }
        Content = new StackPanel { Spacing = Tokens.Space.Base, Children =
        {
            _status, actions,
        } };
        Synchronize();
    }
    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e);
        if (_updates is not null) _updates.Changed += OnChanged;
        Synchronize();
    }
    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
    {
        if (_updates is not null) _updates.Changed -= OnChanged;
        base.OnDetachedFromVisualTree(e);
    }
    private void OnChanged(object? sender, EventArgs e) => Dispatcher.UIThread.Post(Synchronize);
    private void Synchronize()
    {
        var snapshot = _updates?.Snapshot;
        _status.Text = snapshot?.Phase switch
        {
            UpdatePhase.Checking => "Checking for updates…",
            UpdatePhase.Current => $"Freehand {_updates!.CurrentVersion} is up to date",
            UpdatePhase.Available => $"Freehand {snapshot.Package!.Version} is available",
            UpdatePhase.Downloading => $"Downloading Freehand {snapshot.Package!.Version}…",
            UpdatePhase.Ready => "Update ready. Waiting for dictation to finish.",
            UpdatePhase.Installing => "Installing update. Freehand will restart.",
            UpdatePhase.Failed => snapshot.Error,
            _ => _updates is null ? "Development build" : $"Freehand {_updates.CurrentVersion}",
        };
        _status.Foreground = snapshot?.Phase == UpdatePhase.Failed ? Tokens.Brushes.Attention : Tokens.Brushes.Ink;
        _check.IsEnabled = _updates is not null && snapshot?.Phase is not (UpdatePhase.Checking or UpdatePhase.Downloading or UpdatePhase.Ready or UpdatePhase.Installing);
        _update.IsVisible = snapshot?.Package is not null && snapshot.Phase is UpdatePhase.Available or UpdatePhase.Failed;
        if (_later is not null) _later.IsVisible = snapshot?.Phase is UpdatePhase.Available or UpdatePhase.Failed;
    }
}
