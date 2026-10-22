using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using Avalonia.Threading;
using Freehand.App.Views;
using Freehand.Core;
using Freehand.App.Design;

namespace Freehand.App;

/// <summary>Desktop lifecycle, tray and asynchronous shutdown.</summary>
public partial class App : Application
{
    private Composition? _composition;
    private MainWindow? _main;
    private StatusIndicator? _indicator;
    private bool _quitting;
    private Task _quitTask = Task.CompletedTask;
    /// <inheritdoc />
    public override void Initialize() => AvaloniaXamlLoader.Load(this);
    /// <inheritdoc />
    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            _composition = Composition.Create(Program.Desktop);
            _main = new MainWindow(_composition);
            _indicator = new StatusIndicator(_composition.Desktop);
            if (desktop.Args?.Contains("--tray", StringComparer.Ordinal) != true) desktop.MainWindow = _main;
            desktop.ShutdownMode = ShutdownMode.OnExplicitShutdown;
            desktop.ShutdownRequested += (_, e) => { if (!_quitting) { e.Cancel = true; RequestQuit(); } };
            _composition.Changed += (_, _) => Dispatcher.UIThread.Post(SyncFeedback);
            _main.PropertyChanged += (_, e) =>
            {
                if (e.Property == Visual.IsVisibleProperty || e.Property == Window.WindowStateProperty) SyncFeedback();
            };
            if (Program.Desktop is not null)
            {
                Program.Desktop.ActivationRequested += (_, _) => Dispatcher.UIThread.Post(ShowMain);
                Program.Desktop.ShutdownRequested += (_, _) => Dispatcher.UIThread.Post(RequestQuit);
                Program.Desktop.StartNotifications();
            }
            _composition.Start();
            SyncFeedback();
            if (desktop.Args?.Contains("--lifecycle-selftest", StringComparer.Ordinal) == true)
                Dispatcher.UIThread.Post(() => _ = CheckWindowLifecycleAsync(desktop));
            var benchmark = Array.IndexOf(desktop.Args ?? [], "--desktop-benchmark");
            if (benchmark >= 0 && desktop.Args is { } args && benchmark + 1 < args.Length)
                _ = CheckDesktopBenchmarkAsync(desktop, Path.GetFullPath(args[benchmark + 1]));
        }
        base.OnFrameworkInitializationCompleted();
    }
    private void OnTrayShow(object? sender, EventArgs e) => ShowMain();
    private async Task CheckDesktopBenchmarkAsync(IClassicDesktopStyleApplicationLifetime desktop, string output)
    {
        var result = await Task.Run(() => EngineeringChecks.MeasureDesktopAsync(_composition!, output)).ConfigureAwait(false);
        Dispatcher.UIThread.Post(async () => { await _composition!.DisposeAsync().ConfigureAwait(true); _main!.AllowClose = true; _main.Close(); _indicator?.Close(); desktop.Shutdown(result); });
    }
    private async Task CheckWindowLifecycleAsync(IClassicDesktopStyleApplicationLifetime desktop)
    {
        try
        {
            for (var cycle = 0; cycle < 5; cycle++)
            {
                OnTrayShow(null, EventArgs.Empty);
                await Task.Delay(100).ConfigureAwait(true);
                if (_main?.IsVisible != true) throw new InvalidOperationException("Show failed");
                _main.Close();
                if (_main.IsVisible) throw new InvalidOperationException("Close did not hide");
                OnTraySettings(null, EventArgs.Empty);
                await Task.Delay(100).ConfigureAwait(true);
                var settings = desktop.Windows.OfType<SettingsWindow>().Single();
                settings.Close();
                _main.Close();
            }
            Console.WriteLine("  [ok] five hide/reopen and tray Settings cycles; explicit Quit");
            OnTrayQuit(null, EventArgs.Empty);
        }
        catch (Exception e)
        {
            Console.Error.WriteLine("Window lifecycle check failed: " + e);
            if (_composition is not null) await _composition.DisposeAsync().ConfigureAwait(true);
            desktop.Shutdown(1);
        }
    }
    private void OnTraySettings(object? sender, EventArgs e)
    {
        ShowMain();
        if (_main is not null && _composition is not null) _ = new SettingsWindow(_composition.Settings, _composition).ShowDialog(_main);
    }
    private void OnTrayQuit(object? sender, EventArgs e) => RequestQuit();
    private void ShowMain()
    {
        if (_main is null || _quitting) return;
        _main.Show(); _main.WindowState = WindowState.Normal; _main.Activate(); SyncFeedback();
    }
    private void SyncFeedback()
    {
        if (_composition is null || _main is null || _indicator is null || _quitting) return;
        _main.SyncStatus();
        var state = _composition.Engine?.State ?? DictationState.Idle;
        var text = state == DictationState.Idle ? "Freehand ready" : "Freehand " + state.ToString().ToLowerInvariant();
        var icons = TrayIcon.GetIcons(this);
        if (icons is not null) foreach (var icon in icons) icon.ToolTipText = text;
        _indicator.Update(!_main.IsVisible || _main.WindowState == WindowState.Minimized,
            state, _composition.Engine?.Level ?? 0, _composition.Engine?.Feedback);
    }
    private void RequestQuit() { if (!_quitting && _quitTask.IsCompleted) _quitTask = QuitAsync(); }
    private async Task QuitAsync()
    {
        if (ApplicationLifetime is not IClassicDesktopStyleApplicationLifetime desktop) return;
        if (_composition?.Engine?.HasPendingAudio == true && _main is not null)
        {
            ShowMain();
            var dialog = new Window { Title = "Quit Freehand?", Width = Tokens.Size.QuitDialogWidth, SizeToContent = SizeToContent.Height, CanResize = false, WindowStartupLocation = WindowStartupLocation.CenterOwner };
            var quit = new Button { Content = "Discard recording and quit" };
            var stay = new Button { Content = "Keep Freehand running" };
            quit.Click += (_, _) => dialog.Close(true); stay.Click += (_, _) => dialog.Close(false);
            dialog.Content = new StackPanel { Margin = new Thickness(Tokens.Space.Panel), Spacing = Tokens.Space.Wide, Children =
                { new TextBlock { Text = "Quitting will discard the current recording and cancel any pending text delivery.", TextWrapping = Avalonia.Media.TextWrapping.Wrap }, stay, quit } };
            if (!await dialog.ShowDialog<bool>(_main).ConfigureAwait(true)) return;
        }
        _quitting = true;
        try
        {
            _indicator?.Close();
            if (_composition is not null) await _composition.DisposeAsync().ConfigureAwait(true);
        }
        catch (Exception e) { _composition?.Logs.Write(Guid.Empty, "shutdown-" + e.GetType().Name); }
        finally
        {
            if (_main is not null) { _main.AllowClose = true; _main.Close(); }
            _composition = null;
            desktop.Shutdown();
        }
    }
}
