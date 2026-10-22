using System.Globalization;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using Freehand.App.Controls;
using Freehand.App.Design;
using Freehand.Core;

namespace Freehand.App.Views;

/// <summary>The Compact history, dictionary, and settings window.</summary>
public sealed class MainWindow : Window
{
    private readonly Composition? _composition;
    private readonly TranscriptStore? _transcripts;
    private readonly DictionaryFile? _dictionary;
    private readonly AppSettings? _settings;
    private readonly ContentControl _sectionHost = new();
    private readonly Dictionary<string, Button> _tabs = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Border> _tabLines = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Control> _views = new(StringComparer.Ordinal);
    private readonly Button _record = Panels.Button("Record");
    private readonly Lamp _recordLamp = new();
    private readonly DictationActivity _activity = new() { IsVisible = false };
    private readonly TextBlock _recordLabel = Panels.Text("Record", Tokens.Fonts.Control);
    private readonly TextBlock _counter = Panels.Text("00:00", Tokens.Fonts.Label, muted: true);
    private readonly TextBlock _shortcut = Panels.Text("Right Ctrl", Tokens.Fonts.Label, muted: true);
    private readonly TextBlock _status = Panels.Text("", Tokens.Fonts.Control);
    private readonly TextBox _latest = new() { IsReadOnly = true, TextWrapping = TextWrapping.Wrap, MaxHeight = Tokens.Size.TranscriptHeight, AcceptsReturn = true };
    private readonly Button _retry = Panels.Button("Retry", primary: true);
    private readonly Button _discard = Panels.Button("Discard", quiet: true);
    private readonly Button _copy = Panels.Button("Copy", quiet: true);
    private readonly Border _feedback;
    private readonly DispatcherTimer _timer;
    private DateTimeOffset? _startedAt;

    /// <summary>Only explicit application shutdown destroys this window.</summary>
    public bool AllowClose { get; set; }
    /// <summary>Builds an empty window for layout tests.</summary>
    public MainWindow() : this(null) { }
    /// <summary>Builds the window over the existing application services.</summary>
    public MainWindow(Composition? composition) : this(composition, composition?.Transcripts, composition?.Dictionary, composition?.Settings) { }

    internal MainWindow(Composition? composition, TranscriptStore? transcripts, DictionaryFile? dictionary, AppSettings? settings)
    {
        _composition = composition; _transcripts = transcripts; _dictionary = dictionary; _settings = settings;
        Title = "Freehand";
        Width = Tokens.Size.WindowWidth; Height = Tokens.Size.WindowHeight;
        MinWidth = Tokens.Size.MinimumWidth; MinHeight = Tokens.Size.MinimumHeight;
        Background = Tokens.Brushes.Chassis;
        _counter.FontFamily = Tokens.Fonts.Mono;
        _record.Content = new StackPanel
        {
            Orientation = Orientation.Horizontal, Spacing = Tokens.Space.Base,
            Children = { _recordLamp, _recordLabel, _activity, _counter },
        };
        _record.CornerRadius = new CornerRadius(Tokens.Radius.Status);
        _record.Click += (_, _) => ToggleRecording();
        _retry.Click += (_, _) =>
        {
            if (_composition?.Engine?.State == DictationState.AwaitingRetry) _composition.Engine.Retry();
            else _composition?.Engine?.RefreshReadiness();
        };
        _discard.Click += (_, _) => _composition?.Engine?.Discard();
        _copy.Click += async (_, _) =>
        {
            if (Clipboard is not null && _composition?.Engine?.LastResult is { } result)
                await Clipboard.SetTextAsync(result.Text).ConfigureAwait(true);
        };
        _feedback = new Border
        {
            IsVisible = false, Background = Tokens.Brushes.Panel,
            CornerRadius = new CornerRadius(Tokens.Radius.Panel), Padding = new Thickness(Tokens.Space.Roomy),
            Margin = new Thickness(Tokens.Space.Gutter, 0, Tokens.Space.Gutter, 0),
            Child = new StackPanel { Spacing = Tokens.Space.Snug, Children =
            {
                _status, _latest, new StackPanel { Orientation = Orientation.Horizontal, Spacing = Tokens.Space.Snug, Children = { _retry, _discard, _copy } },
            } },
        };
        Content = BuildLayout();
        ShowSection("History");
        _timer = new DispatcherTimer(DispatcherPriority.Background) { Interval = TimeSpan.FromMilliseconds(100) };
        _timer.Tick += (_, _) => SyncFromEngine();
        PropertyChanged += (_, e) =>
        {
            if (e.Property == IsVisibleProperty) { if (IsVisible) _timer.Start(); else _timer.Stop(); }
        };
        Closing += (_, e) => { if (_composition is not null && !AllowClose) { e.Cancel = true; Hide(); } };
        SyncRecording(DictationState.Idle, 0);
        SyncStatus();
    }

    private DockPanel BuildLayout()
    {
        var nav = new StackPanel { Orientation = Orientation.Horizontal, Spacing = Tokens.Space.Snug, HorizontalAlignment = HorizontalAlignment.Center };
        foreach (var section in new[] { "History", "Dictionary", "Settings" })
        {
            var tab = Panels.Button(section, quiet: true);
            tab.Click += (_, _) => ShowSection(section);
            _tabs.Add(section, tab);
            var line = new Border { BorderThickness = new Thickness(0, 0, 0, Tokens.Material.NavigationUnderline), Padding = new Thickness(0, Tokens.Space.Snug), Child = tab };
            _tabLines.Add(section, line); nav.Children.Add(line);
        }
        var wordmark = Panels.Text("Freehand", Tokens.Fonts.Section);
        wordmark.FontWeight = FontWeight.SemiBold;
        var brand = new StackPanel
        {
            Orientation = Orientation.Horizontal, Spacing = Tokens.Space.Base, VerticalAlignment = VerticalAlignment.Center,
            Children =
            {
                new Avalonia.Controls.Shapes.Path
                {
                    Data = Geometry.Parse("M 2 9 V 15 M 7 4 V 20 M 12 1 V 23 M 17 6 V 18 M 22 9 V 15"),
                    Width = Tokens.Size.BrandMark, Height = Tokens.Size.BrandMark,
                    Stroke = Tokens.Brushes.Ink, StrokeThickness = Tokens.Material.IconStroke,
                    StrokeLineCap = PenLineCap.Round, Stretch = Stretch.Uniform,
                },
                wordmark,
            },
        };
        var header = new Grid
        {
            ColumnDefinitions = new ColumnDefinitions("*,Auto,*"),
            Margin = new Thickness(Tokens.Space.Panel, 0), Children = { brand, nav },
        };
        Grid.SetColumn(nav, 1);
        var footer = new Grid
        {
            ColumnDefinitions = new ColumnDefinitions("*,Auto,*"),
            Margin = new Thickness(Tokens.Space.Gutter, Tokens.Space.Roomy), Children = { _record, _shortcut },
        };
        Grid.SetColumn(_record, 1); Grid.SetColumn(_shortcut, 2); _shortcut.HorizontalAlignment = HorizontalAlignment.Right;
        var root = new DockPanel();
        root.Children.Add(Panels.Docked(new Border
        {
            BorderBrush = Tokens.Brushes.Seam, BorderThickness = new Thickness(0, 0, 0, Tokens.Border.Hairline), Child = header,
        }, Dock.Top));
        root.Children.Add(Panels.Docked(footer, Dock.Bottom));
        root.Children.Add(Panels.Docked(_feedback, Dock.Bottom));
        _sectionHost.Margin = new Thickness(Tokens.Space.Gutter, 0);
        _sectionHost.HorizontalContentAlignment = HorizontalAlignment.Stretch;
        _sectionHost.VerticalContentAlignment = VerticalAlignment.Stretch;
        root.Children.Add(_sectionHost);
        return root;
    }

    internal void ShowSection(string section)
    {
        foreach (var (name, tab) in _tabs)
        {
            var selected = string.Equals(name, section, StringComparison.Ordinal);
            CompactTheme.SetButtonResources(tab.Resources, Brushes.Transparent, selected ? Tokens.Brushes.Ink : Tokens.Brushes.Muted);
            tab.FontWeight = selected ? FontWeight.SemiBold : FontWeight.Normal;
            _tabLines[name].BorderBrush = selected ? Tokens.Brushes.Accent : Brushes.Transparent;
            Avalonia.Automation.AutomationProperties.SetName(tab, name + (selected ? ", selected" : ""));
        }
        if (!_views.TryGetValue(section, out var view))
        {
            view = section switch
            {
                "History" when _transcripts is not null => new TranscriptionsView(_transcripts),
                "Dictionary" when _dictionary is not null => new DictionaryView(_dictionary),
                "Settings" when _settings is not null => new SettingsView(_settings, _composition),
                _ => new StackPanel { Children = { Panels.Heading(section), Panels.EmptyState(section == "History" ? "No transcripts yet" : "No entries yet") } },
            };
            _views.Add(section, view);
        }
        _sectionHost.Content = view;
    }

    /// <summary>Updates feedback using the existing dictation state machine.</summary>
    public void SyncStatus()
    {
        var engine = _composition?.Engine;
        if (engine is null) return;
        ApplyFeedback(engine.State, engine.Level, engine.LastResult, engine.Feedback);
    }

    internal void ApplyFeedback(DictationState state, float level, DictationResult? lastResult, DictationFeedback? feedback)
    {
        var attention = state == DictationState.AwaitingRetry || feedback?.Outcome is
            DictationOutcome.CaptureFailure or DictationOutcome.DeliveryFailure or DictationOutcome.EmptySpeech;
        var showTranscript = lastResult is not null && (feedback?.Outcome == DictationOutcome.DeliveryFailure
            || lastResult.Delivery == Freehand.Abstractions.DeliveryOutcome.Disabled || _settings?.Data.KeepHistory == false);
        _feedback.IsVisible = attention || showTranscript;
        _feedback.BorderBrush = Tokens.Brushes.Attention;
        _feedback.BorderThickness = new Thickness(attention ? Tokens.Border.Hairline : 0);
        _status.Foreground = attention ? Tokens.Brushes.Attention : Tokens.Brushes.Ink;
        _status.Text = feedback?.Message ?? state.ToString();
        _latest.Text = lastResult?.Text ?? "";
        _latest.IsVisible = showTranscript; _copy.IsVisible = showTranscript;
        _retry.IsVisible = state == DictationState.AwaitingRetry || feedback?.Outcome == DictationOutcome.CaptureFailure;
        _discard.IsVisible = state == DictationState.AwaitingRetry;
        SyncRecording(state, level);
    }

    private void SyncFromEngine()
    {
        if (_composition?.Engine is not null) SyncStatus();
        var elapsed = _startedAt is null ? TimeSpan.Zero : DateTimeOffset.Now - _startedAt.Value;
        _counter.Text = string.Create(CultureInfo.InvariantCulture, $"{(int)elapsed.TotalMinutes:00}:{elapsed.Seconds:00}");
        if (!IsRecording) _activity.Advance();
    }

    private void SyncRecording(DictationState state, float level)
    {
        IsRecording = state == DictationState.Recording;
        if (IsRecording && _startedAt is null) _startedAt = DateTimeOffset.Now;
        else if (!IsRecording) _startedAt = null;
        var processing = state is DictationState.Preparing or DictationState.Transcribing or DictationState.Recovering or DictationState.Delivering or DictationState.Stopping;
        _recordLamp.IsLit = IsRecording;
        _recordLabel.Text = state switch
        {
            DictationState.Recording => "Stop recording", DictationState.Preparing => "Preparing",
            DictationState.Transcribing => "Transcribing", DictationState.Recovering => "Recovering",
            DictationState.Delivering => "Inserting", DictationState.Stopping => "Finishing", _ => "Record",
        };
        _recordLabel.Foreground = IsRecording ? Tokens.Brushes.Record : Tokens.Brushes.Ink;
        _activity.IsVisible = IsRecording || processing; _activity.Update(state, level);
        _counter.IsVisible = IsRecording;
        _record.IsEnabled = !processing && state != DictationState.AwaitingRetry;
        var key = _settings?.Data.PushToTalkKey ?? 0xA3;
        _shortcut.Text = SettingsView.KeyLabel(key);
    }

    /// <summary>Routes the button through the same engine used by the global hotkey.</summary>
    public void ToggleRecording()
    {
        if (_composition?.Engine is { } engine) { engine.TogglePushToTalk(); SyncFromEngine(); }
        else SyncRecording(IsRecording ? DictationState.Idle : DictationState.Recording, 0);
    }
    /// <summary>Whether the engine is recording.</summary>
    public bool IsRecording { get; private set; }
    /// <summary>The visible recording dot.</summary>
    public Lamp RecordLamp => _recordLamp;
    /// <inheritdoc />
    protected override void OnClosed(EventArgs e) { _timer.Stop(); base.OnClosed(e); }
}
