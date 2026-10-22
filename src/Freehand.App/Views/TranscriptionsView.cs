using System.Globalization;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Freehand.App.Design;
using Freehand.Core;

namespace Freehand.App.Views;

/// <summary>Searchable transcript history using the existing persistent store.</summary>
public sealed class TranscriptionsView : UserControl
{
    private readonly TranscriptStore _store;
    private readonly TextBox _search = Panels.SearchBox("Search history");
    private readonly StackPanel _list = new();
    private readonly TextBlock _count = Panels.Text("", Tokens.Fonts.Label, muted: true);
    private readonly TextBlock _error = Panels.Text("", Tokens.Fonts.Label);
    private readonly Button _older = Panels.Button("Older", quiet: true);
    private readonly Button _newer = Panels.Button("Newer", quiet: true);
    private int _page;

    /// <summary>Builds the view over the transcript store.</summary>
    public TranscriptionsView(TranscriptStore store)
    {
        _store = store;
        _search.TextChanged += (_, _) => { _page = 0; Refresh(); };
        var more = Panels.More("History actions");
        var clear = new MenuItem { Header = "Delete all transcripts" };
        clear.Click += (_, _) => { _store.Clear(); Refresh(); _search.Focus(); };
        more.ContextMenu = new ContextMenu { Items = { clear } };
        more.Click += (_, _) => more.ContextMenu.Open(more);
        _older.Click += (_, _) => { _page++; Refresh(); };
        _newer.Click += (_, _) => { _page = Math.Max(0, _page - 1); Refresh(); };
        _error.Foreground = Tokens.Brushes.Attention;
        Content = new DockPanel
        {
            LastChildFill = true,
            Children =
            {
                Panels.Docked(Panels.Heading("History", more), Dock.Top),
                Panels.Docked(Panels.SearchRow(_search), Dock.Top),
                Panels.Docked(_error, Dock.Bottom),
                Panels.Docked(Panels.Footer(_count, new StackPanel
                {
                    Orientation = Orientation.Horizontal, Spacing = Tokens.Space.Tight, Children = { _newer, _older },
                }), Dock.Bottom),
                new ScrollViewer { Content = _list, HorizontalScrollBarVisibility = Avalonia.Controls.Primitives.ScrollBarVisibility.Disabled },
            },
        };
        Refresh();
    }

    /// <inheritdoc />
    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e); _store.Changed += StoreChanged; Refresh();
    }
    /// <inheritdoc />
    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
    {
        _store.Changed -= StoreChanged; base.OnDetachedFromVisualTree(e);
    }
    private void StoreChanged(object? sender, EventArgs e)
    {
        if (Dispatcher.UIThread.CheckAccess()) Refresh(); else Dispatcher.UIThread.Post(Refresh);
    }

    private void Refresh()
    {
        var records = _store.ReadPage(_search.Text ?? string.Empty, _page);
        _list.Children.Clear();
        _count.Text = string.Create(CultureInfo.CurrentCulture, $"{records.Count} transcripts · Page {_page + 1}");
        _newer.IsEnabled = _page > 0; _older.IsEnabled = records.Count == TranscriptStore.PageSize;
        _error.Text = _store.LastError; _error.IsVisible = !string.IsNullOrEmpty(_store.LastError);
        if (records.Count == 0)
        {
            _list.Children.Add(Panels.EmptyState(string.IsNullOrEmpty(_search.Text) && _page == 0 ? "No transcripts yet" : "No matching transcripts"));
            return;
        }
        foreach (var record in records) _list.Children.Add(BuildRow(record));
    }

    private Border BuildRow(TranscriptRecord record)
    {
        var copy = Panels.Button("Copy", quiet: true);
        copy.Click += async (_, _) =>
        {
            var clipboard = TopLevel.GetTopLevel(this)?.Clipboard;
            if (clipboard is null) return;
            await clipboard.SetTextAsync(record.Text).ConfigureAwait(true);
            copy.Content = "Copied";
            await Task.Delay(TimeSpan.FromSeconds(1.4)).ConfigureAwait(true);
            copy.Content = "Copy";
        };
        var more = Panels.More("Transcript actions");
        var delete = new MenuItem { Header = "Delete transcript" };
        delete.Click += (_, _) => { _store.Remove(record.Id); _search.Focus(); };
        more.ContextMenu = new ContextMenu { Items = { delete } };
        more.Click += (_, _) => more.ContextMenu.Open(more);
        var day = record.At.LocalDateTime.Date;
        var date = day == DateTime.Today ? "Today" : day == DateTime.Today.AddDays(-1) ? "Yesterday" : day.ToString("d", CultureInfo.CurrentCulture);
        var body = new StackPanel { Spacing = Tokens.Space.Snug, Children =
        {
            Panels.Text(date + "  " + record.At.ToLocalTime().ToString("t", CultureInfo.CurrentCulture), Tokens.Fonts.Label, muted: true),
            new SelectableTextBlock
            {
                Text = record.Text, FontFamily = Tokens.Fonts.Grotesque, FontSize = Tokens.Fonts.Transcript,
                LineHeight = Tokens.Fonts.TranscriptLine, Foreground = Tokens.Brushes.Ink, TextWrapping = TextWrapping.Wrap,
                SelectionBrush = Tokens.Brushes.Accent, SelectionForegroundBrush = Tokens.Brushes.AccentInk,
            },
        } };
        if (record.Corrections is { Count: > 0 } corrections)
            body.Children.Add(Panels.Text(string.Join(" · ", corrections.Select(c => c.Count > 1
                ? $"{c.From} → {c.To} ×{c.Count}" : $"{c.From} → {c.To}")), Tokens.Fonts.Label, muted: true));
        var row = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto"), ColumnSpacing = Tokens.Space.Roomy };
        row.Children.Add(body);
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = Tokens.Space.Tight, VerticalAlignment = VerticalAlignment.Center, Children = { copy, more } };
        Grid.SetColumn(actions, 1); row.Children.Add(actions);
        return Panels.Row(row);
    }
}
