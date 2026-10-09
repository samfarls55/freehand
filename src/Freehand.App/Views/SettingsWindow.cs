using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Freehand.App.Controls;
using Freehand.App.Design;
using Freehand.Core;
using Freehand.Speech;
using Avalonia.Threading;

namespace Freehand.App.Views;

/// <summary>Settings: the hotkey and the model.</summary>
public sealed class SettingsWindow : Window
{
    /// <summary>
    /// The keys offered, in recommendation order.
    /// </summary>
    /// <remarks>
    /// Right Alt is included but listed last and carries a warning: on German, Polish, UK,
    /// Nordic and most Latin-American layouts it is AltGr, and binding push-to-talk there
    /// breaks typing <c>@</c>, <c>€</c>, <c>\</c> and <c>|</c>.
    /// </remarks>
    private static readonly (int Key, string Label, string? Warning)[] Keys =
    [
        (0xA3, "RIGHT CTRL", null),
        (0xA1, "RIGHT SHIFT", null),
        (0x14, "CAPS LOCK", null),
        (0x7C, "F13", null),
        (0xA5, "RIGHT ALT", "Right Alt is AltGr on many European layouts — binding it here "
                          + "will interfere with typing @, €, \\ and |."),
    ];

    private readonly AppSettings _settings;
    private readonly StackPanel _keyRow;
    private readonly TextBlock _keyWarning;
    private readonly Composition? _composition;
    private readonly ContentControl _modelHost = new();

    /// <summary>Builds the settings window.</summary>
    public SettingsWindow(AppSettings settings, Composition? composition = null)
    {
        _settings = settings;
        _composition = composition;

        Title = "Freehand Settings";
        Width = 540;
        SizeToContent = SizeToContent.Height;
        CanResize = false;
        Background = Tokens.Brushes.Chassis;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;

        _keyRow = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Spacing = Tokens.Space.Snug,
        };

        _keyWarning = new TextBlock
        {
            FontFamily = Tokens.Fonts.Grotesque,
            FontSize = Tokens.Fonts.Label,
            Foreground = new SolidColorBrush(Tokens.Colors.MeterAmber),
            TextWrapping = TextWrapping.Wrap,
            IsVisible = false,
        };

        foreach (var (key, label, warning) in Keys)
        {
            var button = new TransportKey { Content = label, EngagedColor = Tokens.Colors.Ink };
            button.Click += (_, _) => SelectKey(key, warning);
            _keyRow.Children.Add(button);
        }

        Content = BuildContent();
        SelectKey(_settings.Data.PushToTalkKey, WarningFor(_settings.Data.PushToTalkKey));
        if (_composition is not null)
        {
            _composition.Changed += ModelChanged;
            Closed += (_, _) => _composition.Changed -= ModelChanged;
        }
    }
    private void ModelChanged(object? sender, EventArgs e) => Dispatcher.UIThread.Post(() => _modelHost.Content = BuildModelStatus());

    private static string? WarningFor(int key) =>
        Keys.FirstOrDefault(k => k.Key == key).Warning;

    private StackPanel BuildContent() => new StackPanel
    {
        Margin = new Thickness(Tokens.Space.Panel),
        Spacing = Tokens.Space.Wide,
        Children =
        {
            Section("PUSH TO TALK", new StackPanel
            {
                Spacing = Tokens.Space.Snug,
                Children =
                {
                    _keyRow,
                    _keyWarning,
                    Note("Hold this key anywhere to dictate. The key is passed through to the "
                       + "focused app rather than swallowed, so it never gets stuck down."),
                },
            }),

            Section("MODEL", BuildModelSection()),

            Section("BEHAVIOUR", new StackPanel
            {
                Spacing = Tokens.Space.Snug,
                Children =
                {
                    Toggle("Type transcripts into the focused app", _settings.Data.InjectText,
                        v => Save(_settings.Data with { InjectText = v })),
                    Toggle("Keep a transcript history", _settings.Data.KeepHistory,
                        v => Save(_settings.Data with { KeepHistory = v })),
                    Toggle("Start at Windows login", _settings.Data.StartAtLogin,
                        v => Save(_settings.Data with { StartAtLogin = v })),
                    Note("Release model memory after this many idle minutes:"),
                    IdleTimeoutControl(),
                    Note("Changes made during dictation apply when it finishes."),
                    LogButton(),
                },
            }),
        },
    };

    private StackPanel BuildModelSection()
    {
        _modelHost.Content = BuildModelStatus();
        var bundled = new Button { Content = "Use bundled model" };
        bundled.Click += (_, _) => Save(_settings.Data with { ModelDirectory = null });
        var repair = new Button { Content = "Repair bundled model" };
        repair.Click += (_, _) =>
        {
            var installer = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Freehand", "installer", "FreehandSetup.exe");
            _composition?.Desktop?.Open(File.Exists(installer) ? installer : "ms-settings:appsfeatures");
        };
        return new StackPanel { Spacing = Tokens.Space.Snug, Children = { _modelHost, bundled, repair } };
    }
    private StackPanel BuildModelStatus()
    {
        var located = _composition?.Models.ResolvedDirectory ?? _settings.Data.ModelDirectory ?? Path.Combine(AppContext.BaseDirectory, "models", "parakeet-v2");
        var found = _composition?.Models.IsVerified ?? ParakeetTranscriber.IsComplete(located);
        var state = _composition?.Speech?.State ?? Freehand.Abstractions.ModelState.Unloaded;

        var status = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Spacing = Tokens.Space.Snug,
            Children =
            {
                new Lamp
                {
                    IsLit = found,
                    LampColor = found ? Tokens.Colors.MeterGreen : Tokens.Colors.MeterAmber,
                    VerticalAlignment = VerticalAlignment.Center,
                },
                new TextBlock
                {
                    Text = found ? state switch
                    {
                        Freehand.Abstractions.ModelState.Unloaded => "Installed · loads when you dictate",
                        Freehand.Abstractions.ModelState.Ready => "Installed · loaded",
                        Freehand.Abstractions.ModelState.Starting or Freehand.Abstractions.ModelState.Loading => "Installed · preparing",
                        Freehand.Abstractions.ModelState.Stopping => "Installed · releasing memory",
                        _ => "Installed · last load failed",
                    } : "Model needs verification or repair",
                    FontFamily = Tokens.Fonts.Grotesque,
                    FontSize = Tokens.Fonts.Body,
                    Foreground = Tokens.Brushes.Ink,
                    VerticalAlignment = VerticalAlignment.Center,
                },
            },
        };

        var detail = Note(located + (found ? "" : "\n" + (_composition?.Models.Error ?? "Run the installer again to verify and repair the bundled model.")));

        return new StackPanel { Spacing = Tokens.Space.Snug, Children = { status, detail } };
    }
    private NumericUpDown IdleTimeoutControl()
    {
        var input = new NumericUpDown { Minimum = 1, Maximum = 60, Increment = 1, Value = _settings.Data.IdleModelMinutes };
        input.ValueChanged += (_, _) => Save(_settings.Data with { IdleModelMinutes = (int)(input.Value ?? 5) });
        return input;
    }
    private Button LogButton()
    {
        var button = new Button { Content = "Open diagnostic logs" };
        button.Click += (_, _) =>
        {
            if (_composition is null) return;
            Directory.CreateDirectory(_composition.Logs.DirectoryPath);
            _composition.Desktop?.Open(_composition.Logs.DirectoryPath);
        };
        return button;
    }

    private void SelectKey(int key, string? warning)
    {
        for (var i = 0; i < Keys.Length; i++)
        {
            ((TransportKey)_keyRow.Children[i]).IsEngaged = Keys[i].Key == key;
        }

        _keyWarning.Text = warning ?? string.Empty;
        _keyWarning.IsVisible = warning is not null;

        if (_settings.Data.PushToTalkKey != key) Save(_settings.Data with { PushToTalkKey = key });
    }

    private void Save(SettingsData data)
    {
        if (_settings.TryUpdate(data)) return;
        _keyWarning.Text = _settings.LastError; _keyWarning.IsVisible = true;
    }

    private static BrushedPanel Section(string label, Control content) => new BrushedPanel
    {
        Child = new StackPanel
        {
            Margin = new Thickness(Tokens.Space.Roomy),
            Spacing = Tokens.Space.Base,
            Children = { new Silkscreen { Text = label, IsLarge = true }, content },
        },
    };

    private static TextBlock Note(string text) => new()
    {
        Text = text,
        FontFamily = Tokens.Fonts.Grotesque,
        FontSize = Tokens.Fonts.Label,
        Foreground = new SolidColorBrush(Tokens.Colors.InkSecondary),
        TextWrapping = TextWrapping.Wrap,
    };

    private static CheckBox Toggle(string label, bool value, Action<bool> onChange)
    {
        var box = new CheckBox
        {
            IsChecked = value,
            Content = new TextBlock
            {
                Text = label,
                FontFamily = Tokens.Fonts.Grotesque,
                FontSize = Tokens.Fonts.Body,
                Foreground = Tokens.Brushes.Ink,
            },
        };

        box.IsCheckedChanged += (_, _) => onChange(box.IsChecked ?? false);
        return box;
    }
}
