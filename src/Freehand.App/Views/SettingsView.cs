using Avalonia;
using Avalonia.Automation;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Freehand.Abstractions;
using Freehand.App.Controls;
using Freehand.App.Design;
using Freehand.Core;
using Freehand.Speech;

namespace Freehand.App.Views;

/// <summary>Native settings shared by the main tab and tray settings window.</summary>
public sealed class SettingsView : UserControl
{
    private readonly AppSettings _settings;
    private readonly Composition? _composition;
    private readonly HotkeyEditor _key;
    private readonly ToggleSwitch _inject = Switch("Insert text into the focused app");
    private readonly ToggleSwitch _history = Switch("Keep transcript history");
    private readonly ToggleSwitch _login = Switch("Start at Windows login");
    private readonly ToggleSwitch _updates = Switch("Check for updates automatically");
    private readonly NumericUpDown _idle = new() { Minimum = 1, Maximum = 60, Increment = 1, Width = 100 };
    private readonly TextBlock _warning = Panels.Text("", Tokens.Fonts.Label);
    private readonly TextBlock _error = Panels.Text("", Tokens.Fonts.Label);
    private readonly TextBlock _modelStatus = Panels.Text("");
    private readonly TextBlock _modelPath = Panels.Text("", Tokens.Fonts.Label, muted: true);
    private readonly DispatcherTimer _modelTimer = new() { Interval = TimeSpan.FromSeconds(1) };
    private bool _syncing;

    /// <summary>Builds settings using the existing persistence and preference coordinator.</summary>
    public SettingsView(AppSettings settings, Composition? composition = null) : this(settings, composition, composition) { }

    internal SettingsView(AppSettings settings, Composition? composition, IHotkeyRecorder? recorder)
    {
        _settings = settings; _composition = composition;
        _key = new HotkeyEditor(recorder, keys => Save(_settings.Data with { PushToTalkKey = keys[0], PushToTalkKeys = keys.ToArray() }));
        AutomationProperties.SetName(_idle, "Release model after idle minutes");
        _warning.Foreground = Tokens.Brushes.Attention; _error.Foreground = Tokens.Brushes.Attention;
        _inject.IsCheckedChanged += (_, _) => { if (!_syncing) Save(_settings.Data with { InjectText = _inject.IsChecked == true }); };
        _history.IsCheckedChanged += (_, _) => { if (!_syncing) Save(_settings.Data with { KeepHistory = _history.IsChecked == true }); };
        _login.IsCheckedChanged += (_, _) => { if (!_syncing) Save(_settings.Data with { StartAtLogin = _login.IsChecked == true }); };
        _updates.IsCheckedChanged += (_, _) => { if (!_syncing) Save(_settings.Data with { CheckForUpdates = _updates.IsChecked == true }); };
        _idle.ValueChanged += (_, _) => { if (!_syncing && _idle.Value is { } value) Save(_settings.Data with { IdleModelMinutes = (int)value }); };
        _modelTimer.Tick += (_, _) => UpdateModelStatus();
        Content = new DockPanel { Children =
        {
            Panels.Docked(Panels.Heading("Settings"), Dock.Top),
            new ScrollViewer { HorizontalScrollBarVisibility = Avalonia.Controls.Primitives.ScrollBarVisibility.Disabled,
                Content = new StackPanel { Spacing = Tokens.Space.Wide, Children =
                {
                    _error,
                    Group("Dictation", new StackPanel { Children =
                    {
                        SettingRow("Push-to-talk key", _key), _warning,
                        SettingRow("Insert text into the focused app", _inject),
                        SettingRow("Keep transcript history", _history),
                    } }),
                    Group("System", new StackPanel { Children =
                    {
                        SettingRow("Start at Windows login", _login),
                        SettingRow("Release model after idle minutes", _idle),
                    } }),
                    Group("Speech model", BuildModelSection()),
                    Group("Updates", new StackPanel { Spacing = Tokens.Space.Base, Children =
                    {
                        SettingRow("Check for updates automatically", _updates), new UpdateView(_composition?.Updates),
                    } }),
                    Panels.Text("Changes made during dictation apply when it finishes.", Tokens.Fonts.Label, muted: true),
                } },
            },
        } };
        Synchronize();
    }

    /// <inheritdoc />
    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e); _settings.Changed += SettingsChanged; Synchronize(); _modelTimer.Start();
    }
    /// <inheritdoc />
    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
    {
        _modelTimer.Stop(); _settings.Changed -= SettingsChanged; base.OnDetachedFromVisualTree(e);
    }
    private void SettingsChanged(object? sender, EventArgs e)
    {
        if (Dispatcher.UIThread.CheckAccess()) Synchronize(); else Dispatcher.UIThread.Post(Synchronize);
    }
    private void Synchronize()
    {
        _syncing = true;
        try
        {
            _key.Synchronize(_settings.Data.DictationKeys);
            _inject.IsChecked = _settings.Data.InjectText; _history.IsChecked = _settings.Data.KeepHistory;
            _login.IsChecked = _settings.Data.StartAtLogin; _idle.Value = _settings.Data.IdleModelMinutes;
            _updates.IsChecked = _settings.Data.CheckForUpdates;
            _warning.Text = _settings.Data.DictationKeys.Contains(0xA5) ? "Right Alt is AltGr on many European layouts. This can interfere with typing @, €, \\ and |." : "";
            _warning.IsVisible = !string.IsNullOrEmpty(_warning.Text);
            _error.Text = _settings.LastError; _error.IsVisible = !string.IsNullOrEmpty(_error.Text);
            UpdateModelStatus();
        }
        finally { _syncing = false; }
    }
    private void Save(SettingsData data) { _settings.TryUpdate(data); Synchronize(); }

    private StackPanel BuildModelSection()
    {
        var bundled = Panels.Button("Use bundled model", quiet: true);
        bundled.Click += (_, _) => Save(_settings.Data with { ModelDirectory = null });
        var repair = Panels.Button("Repair model", quiet: true);
        repair.Click += (_, _) =>
        {
            var installer = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Freehand", "installer", "FreehandSetup.exe");
            _composition?.Desktop?.Open(File.Exists(installer) ? installer : "ms-settings:appsfeatures");
        };
        var logs = Panels.Button("Open diagnostic logs", quiet: true);
        logs.Click += (_, _) =>
        {
            if (_composition is null) return;
            Directory.CreateDirectory(_composition.Logs.DirectoryPath); _composition.Desktop?.Open(_composition.Logs.DirectoryPath);
        };
        // A standalone headless view cannot launch platform actions.
        repair.IsEnabled = _composition is not null; logs.IsEnabled = _composition is not null;
        return new StackPanel { Spacing = Tokens.Space.Base, Children =
        {
            Panels.Text(ModelResolver.DisplayName, Tokens.Fonts.Section), _modelStatus,
            new Expander { Header = "Model details", HorizontalAlignment = HorizontalAlignment.Stretch,
                Content = new StackPanel { Spacing = Tokens.Space.Base, Children =
                {
                    _modelPath,
                    new WrapPanel { ItemSpacing = Tokens.Space.Snug, LineSpacing = Tokens.Space.Snug, Children = { bundled, repair, logs } },
                } },
            },
        } };
    }
    private void UpdateModelStatus()
    {
        var located = _composition?.Models.ResolvedDirectory ?? _settings.Data.ModelDirectory ?? Path.Combine(AppContext.BaseDirectory, "models", ModelResolver.DirectoryName);
        var found = _composition?.Models.IsVerified ?? ParakeetTranscriber.IsComplete(located);
        var state = _composition?.Speech?.State ?? Freehand.Abstractions.ModelState.Unloaded;
        _modelStatus.Text = found ? state switch
        {
            Freehand.Abstractions.ModelState.Unloaded => "Installed · loads when you dictate",
            Freehand.Abstractions.ModelState.Ready => "Installed · loaded",
            Freehand.Abstractions.ModelState.Starting or Freehand.Abstractions.ModelState.Loading => "Installed · preparing",
            Freehand.Abstractions.ModelState.Stopping => "Installed · releasing memory",
            _ => "Installed · last load failed",
        } : "Model needs verification or repair";
        _modelStatus.Foreground = found ? Tokens.Brushes.Muted : Tokens.Brushes.Attention;
        _modelPath.Text = located + (found ? "" : "\n" + (_composition?.Models.Error ?? "Run the installer again to verify and repair the bundled model."));
    }
    private static ToggleSwitch Switch(string label)
    {
        var toggle = new ToggleSwitch { OnContent = null, OffContent = null, VerticalAlignment = VerticalAlignment.Center };
        AutomationProperties.SetName(toggle, label); return toggle;
    }
    private static Border SettingRow(string label, Control input)
    {
        var grid = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto"), ColumnSpacing = Tokens.Space.Wide };
        grid.Children.Add(Panels.Text(label)); Grid.SetColumn(input, 1); grid.Children.Add(input);
        return new Border { Padding = new Thickness(0, Tokens.Space.Base), Child = grid };
    }
    private static StackPanel Group(string title, Control content) => new StackPanel
    {
        Spacing = Tokens.Space.Base, Children =
        {
            Panels.Text(title, Tokens.Fonts.Section),
            new Border { Background = Tokens.Brushes.Panel, CornerRadius = new CornerRadius(Tokens.Radius.Panel), Padding = new Thickness(Tokens.Space.Roomy, Tokens.Space.Snug), Child = content },
        },
    };
}
