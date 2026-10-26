using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Freehand.App.Design;
using Freehand.Dictionary;
using Freehand.Core;

namespace Freehand.App.Views;

/// <summary>Search, edit, and enable the existing dictionary entries.</summary>
public sealed class DictionaryView : UserControl
{
    private readonly DictionaryFile _file;
    private readonly TextBox _search = Panels.SearchBox("Search dictionary");
    private readonly StackPanel _list = new();
    private readonly TextBlock _count = Panels.Text("", Tokens.Fonts.Label, muted: true);
    private readonly TextBlock _error = Panels.Text("", Tokens.Fonts.Label);

    /// <summary>Builds the dictionary view.</summary>
    public DictionaryView(DictionaryFile file)
    {
        _file = file;
        _search.TextChanged += (_, _) => Refresh();
        var add = Panels.Button("Add entry", primary: true);
        add.Click += (_, _) => ShowEditor(null);
        var reveal = Panels.Button("Open dictionary.txt", quiet: true);
        reveal.Click += (_, _) => OpenInEditor(_file.FilePath);
        _error.Foreground = Tokens.Brushes.Attention;
        Content = new DockPanel { Children =
        {
            Panels.Docked(Panels.Heading("Dictionary", add), Dock.Top),
            Panels.Docked(Panels.SearchRow(_search), Dock.Top),
            Panels.Docked(_error, Dock.Bottom),
            Panels.Docked(Panels.Footer(_count, reveal), Dock.Bottom),
            new ScrollViewer { Content = _list, HorizontalScrollBarVisibility = Avalonia.Controls.Primitives.ScrollBarVisibility.Disabled },
        } };
        Refresh();
    }
    /// <inheritdoc />
    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e); _file.Changed += FileChanged; Refresh();
    }
    /// <inheritdoc />
    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
    {
        _file.Changed -= FileChanged; base.OnDetachedFromVisualTree(e);
    }
    private void FileChanged(object? sender, EventArgs e)
    {
        if (Dispatcher.UIThread.CheckAccess()) Refresh(); else Dispatcher.UIThread.Post(Refresh);
    }
    private void Refresh()
    {
        var entries = _file.Search(_search.Text ?? string.Empty);
        _list.Children.Clear();
        _count.Text = string.Create(System.Globalization.CultureInfo.CurrentCulture, $"{_file.Entries.Count} entries");
        _error.Text = _file.LastError; _error.IsVisible = !string.IsNullOrEmpty(_error.Text);
        if (entries.Count == 0) _list.Children.Add(Panels.EmptyState(_file.Entries.Count == 0 ? "No dictionary entries yet" : "No matching entries"));
        foreach (var entry in entries) _list.Children.Add(BuildRow(entry));
    }
    private Border BuildRow(DictionaryEntry entry)
    {
        var enabled = new ToggleSwitch { Tag = entry.Id, IsChecked = entry.IsEnabled, OnContent = null, OffContent = null, VerticalAlignment = VerticalAlignment.Center };
        Avalonia.Automation.AutomationProperties.SetName(enabled, "Enable " + entry.Write);
        enabled.IsCheckedChanged += (_, _) =>
        {
            _file.Update(entry with { IsEnabled = enabled.IsChecked == true });
            Dispatcher.UIThread.Post(() =>
            {
                var replacement = this.GetVisualDescendants().OfType<ToggleSwitch>()
                    .FirstOrDefault(t => Equals(t.Tag, entry.Id));
                if (replacement is not null) replacement.Focus(); else _search.Focus();
            }, DispatcherPriority.Loaded);
        };
        var edit = Panels.Button("Edit", quiet: true);
        edit.Click += (_, _) => ShowEditor(entry);
        var more = Panels.More("Entry actions");
        var delete = new MenuItem { Header = "Delete entry" };
        delete.Click += (_, _) => { _file.Remove(entry.Id); _search.Focus(); };
        more.ContextMenu = new ContextMenu { Items = { delete } };
        more.Click += (_, _) => more.ContextMenu.Open(more);
        var row = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto"), ColumnSpacing = Tokens.Space.Roomy };
        row.Children.Add(new StackPanel { Spacing = Tokens.Space.Tight, Opacity = entry.IsEnabled ? 1 : 0.65, Children =
        {
            Panels.Text(entry.Kind == EntryKind.Correction ? $"{entry.Hear} → {entry.Write}" : entry.Write),
            Panels.Text(entry.Kind == EntryKind.Correction ? "Correction" : "Saved term", Tokens.Fonts.Label, muted: true),
        } });
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = Tokens.Space.Tight, Children = { enabled, edit, more } };
        Grid.SetColumn(actions, 1); row.Children.Add(actions);
        return Panels.Row(row);
    }
    private void ShowEditor(DictionaryEntry? entry)
    {
        if (TopLevel.GetTopLevel(this) is not Window owner) return;
        var editor = new DictionaryEditorWindow(entry);
        editor.Saved += (_, saved) => { if (entry is null) _file.Add(saved); else _file.Update(saved); };
        _ = editor.ShowDialog(owner);
    }
    private static void OpenInEditor(string path)
    {
        try
        {
            if (!File.Exists(path)) { Directory.CreateDirectory(Path.GetDirectoryName(path)!); File.WriteAllText(path, string.Empty); }
            using var process = new System.Diagnostics.Process();
            process.StartInfo = new System.Diagnostics.ProcessStartInfo(path) { UseShellExecute = true };
            process.Start();
        }
        catch (Exception e) when (e is System.ComponentModel.Win32Exception or IOException or UnauthorizedAccessException) { }
    }
}

/// <summary>Edits a term or literal correction, preserving the dictionary behavior contract.</summary>
public sealed class DictionaryEditorWindow : Window
{
    private readonly Button _term = Panels.Button("Term", quiet: true);
    private readonly Button _correction = Panels.Button("Correction", quiet: true);
    private readonly TextBox _hear;
    private readonly TextBox _write;
    private readonly Control _hearField;
    private readonly TextBlock _writeLabel = Panels.Text("Word or phrase", Tokens.Fonts.Label, muted: true);
    private readonly StackPanel _warnings = new() { Spacing = Tokens.Space.Snug };
    private readonly Button _save = Panels.Button("Save entry", primary: true);
    private readonly Guid _id;
    private readonly bool _wasEnabled;
    private EntryKind _kind;
    /// <summary>Raised with the same dictionary entry format used by the existing store.</summary>
    public event EventHandler<DictionaryEntry>? Saved;
    /// <summary>Builds an editor for a new or existing entry.</summary>
    public DictionaryEditorWindow(DictionaryEntry? entry)
    {
        _id = entry?.Id ?? Guid.NewGuid(); _wasEnabled = entry?.IsEnabled ?? true; _kind = entry?.Kind ?? EntryKind.Term;
        Title = entry is null ? "New dictionary entry" : "Edit dictionary entry";
        Width = 500; SizeToContent = SizeToContent.Height; CanResize = false;
        Background = Tokens.Brushes.Chassis; WindowStartupLocation = WindowStartupLocation.CenterOwner;
        _hear = new TextBox { Text = entry?.Hear ?? "", Watermark = "cloud code" };
        _write = new TextBox { Text = entry?.Write ?? "", Watermark = "Claude Code" };
        Avalonia.Automation.AutomationProperties.SetName(_hear, "When you hear");
        Avalonia.Automation.AutomationProperties.SetName(_write, "Write");
        _hearField = Panels.Labelled("When you hear", _hear);
        _term.Click += (_, _) => SetKind(EntryKind.Term);
        _correction.Click += (_, _) => SetKind(EntryKind.Correction);
        _hear.TextChanged += (_, _) => Revalidate(); _write.TextChanged += (_, _) => Revalidate();
        var cancel = Panels.Button("Cancel", quiet: true); cancel.IsCancel = true; cancel.Click += (_, _) => Close();
        _save.IsDefault = true;
        _save.Click += (_, _) => { if (IsValid) { Saved?.Invoke(this, Draft); Close(); } };
        Content = new StackPanel { Margin = new Thickness(Tokens.Space.Panel), Spacing = Tokens.Space.Wide, Children =
        {
            new StackPanel { Orientation = Orientation.Horizontal, Spacing = Tokens.Space.Snug, Children = { _term, _correction } },
            _hearField,
            new StackPanel { Spacing = Tokens.Space.Snug, Children = { _writeLabel, _write } },
            _warnings,
            new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Spacing = Tokens.Space.Snug, Children = { cancel, _save } },
        } };
        SetKind(_kind);
        Opened += (_, _) => { if (_kind == EntryKind.Correction) _hear.Focus(); else _write.Focus(); };
    }
    private DictionaryEntry Draft => new()
    {
        Id = _id, Kind = _kind, Write = (_write.Text ?? "").Trim(),
        Hear = _kind == EntryKind.Correction ? (_hear.Text ?? "").Trim() : "", IsEnabled = _wasEnabled,
    };
    private bool IsValid => Draft.Write.Length > 0 && (_kind == EntryKind.Term || Draft.Hear.Length > 0);
    private void SetKind(EntryKind kind)
    {
        _kind = kind; Panels.Select(_term, kind == EntryKind.Term); Panels.Select(_correction, kind == EntryKind.Correction);
        _hearField.IsVisible = kind == EntryKind.Correction;
        _writeLabel.Text = kind == EntryKind.Correction ? "Write" : "Word or phrase";
        Revalidate();
    }
    private void Revalidate()
    {
        _warnings.Children.Clear();
        foreach (var warning in DictionaryWarning.Check(Draft))
        {
            var label = Panels.Text(warning.Message, Tokens.Fonts.Label); label.Foreground = Tokens.Brushes.Attention;
            _warnings.Children.Add(label);
        }
        _save.IsEnabled = IsValid;
    }
}
