using Avalonia;
using Avalonia.Automation;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Freehand.App.Design;

namespace Freehand.App.Views;

/// <summary>Shared layout and control factories.</summary>
internal static class Panels
{
    public static TextBlock Text(string text, double size = Tokens.Fonts.Body, bool muted = false) => new()
    {
        Text = text, FontFamily = Tokens.Fonts.Grotesque, FontSize = size,
        Foreground = muted ? Tokens.Brushes.Muted : Tokens.Brushes.Ink,
        VerticalAlignment = VerticalAlignment.Center, TextWrapping = TextWrapping.Wrap,
    };

    public static TextBox SearchBox(string placeholder)
    {
        var search = new TextBox
        {
            Watermark = placeholder, HorizontalAlignment = HorizontalAlignment.Stretch,
            InnerLeftContent = new Avalonia.Controls.Shapes.Path
            {
                Data = Geometry.Parse("M 15 15 L 21 21 M 17 10 A 7 7 0 1 1 3 10 A 7 7 0 1 1 17 10"),
                Stroke = Tokens.Brushes.Muted, StrokeThickness = 1.5, Width = 18, Height = 18,
                Stretch = Stretch.Uniform, Margin = new Thickness(Tokens.Space.Base, 0, Tokens.Space.Tight, 0),
                VerticalAlignment = VerticalAlignment.Center,
            },
        };
        AutomationProperties.SetName(search, placeholder);
        return search;
    }

    public static Button Button(string label, bool primary = false, bool quiet = false)
    {
        var button = new Button { Content = label, VerticalAlignment = VerticalAlignment.Center };
        if (primary) button.Classes.Add("accent");
        else if (quiet) CompactTheme.SetButtonResources(button.Resources, Brushes.Transparent, Tokens.Brushes.Muted);
        return button;
    }

    public static Button More(string name)
    {
        var button = Button("", quiet: true);
        var dots = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 3 };
        for (var i = 0; i < 3; i++) dots.Children.Add(new Avalonia.Controls.Shapes.Ellipse { Width = 3, Height = 3, Fill = Tokens.Brushes.Muted });
        button.Content = dots;
        AutomationProperties.SetName(button, name); ToolTip.SetTip(button, name);
        return button;
    }

    public static void Select(Button button, bool selected)
    {
        CompactTheme.SetButtonResources(button.Resources,
            selected ? Tokens.Brushes.Accent : Brushes.Transparent,
            selected ? Tokens.Brushes.AccentInk : Tokens.Brushes.Muted);
        if (selected) foreach (var state in new[] { "PointerOver", "Pressed" }) button.Resources["ButtonBackground" + state] = Tokens.Brushes.Accent;
        button.FontWeight = selected ? FontWeight.SemiBold : FontWeight.Normal;
        AutomationProperties.SetName(button, button.Content + (selected ? ", selected" : ""));
    }

    public static Border SearchRow(Control search, params Control[] trailing)
    {
        var row = new DockPanel();
        foreach (var control in trailing.Reverse())
        {
            control.Margin = new Thickness(Tokens.Space.Snug, 0, 0, 0);
            row.Children.Add(Docked(control, Dock.Right));
        }
        row.Children.Add(search);
        return new Border { Padding = new Thickness(0, Tokens.Space.Wide, 0, Tokens.Space.Base), Child = row };
    }

    public static Border Row(Control content) => new()
    {
        BorderBrush = Tokens.Brushes.Seam, BorderThickness = new Thickness(0, 0, 0, Tokens.Border.Hairline),
        Padding = new Thickness(0, Tokens.Space.Roomy), Child = content,
    };

    public static Control EmptyState(string label) => new Border
    {
        Padding = new Thickness(0, Tokens.Space.Gutter),
        Child = Text(label, Tokens.Fonts.Section, muted: true),
    };

    public static Control Docked(Control control, Dock side) { DockPanel.SetDock(control, side); return control; }

    public static StackPanel Labelled(string label, Control content) => new()
    {
        Spacing = Tokens.Space.Snug, Children = { Text(label, Tokens.Fonts.Label, muted: true), content },
    };
}
