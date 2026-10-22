using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Media;
using Avalonia.Styling;

namespace Freehand.App.Design;

/// <summary>Compact styling over the native Fluent control templates.</summary>
internal sealed class CompactTheme : Styles
{
    public CompactTheme()
    {
        Resources["SystemAccentColor"] = Tokens.Colors.Accent;
        Resources["SystemControlHighlightAccentBrush"] = Tokens.Brushes.Accent;
        Resources["SystemControlForegroundBaseHighBrush"] = Tokens.Brushes.Ink;
        Resources["SystemControlForegroundBaseMediumBrush"] = Tokens.Brushes.Muted;
        Resources["TextControlPlaceholderForeground"] = Tokens.Brushes.Muted;
        Resources["TextControlPlaceholderForegroundFocused"] = Tokens.Brushes.Muted;
        Resources["TextControlPlaceholderForegroundPointerOver"] = Tokens.Brushes.Muted;
        Resources["TextControlBackground"] = Tokens.Brushes.Panel;
        Resources["TextControlBackgroundPointerOver"] = Tokens.Brushes.Cap;
        Resources["TextControlBackgroundFocused"] = Tokens.Brushes.Panel;
        Resources["TextControlBorderBrush"] = Tokens.Brushes.Seam;
        Resources["TextControlBorderBrushPointerOver"] = Tokens.Brushes.Muted;
        Resources["TextControlBorderBrushFocused"] = Tokens.Brushes.Accent;
        Resources["TextControlForeground"] = Tokens.Brushes.Ink;
        Resources["TextControlForegroundFocused"] = Tokens.Brushes.Ink;
        Resources["TextControlForegroundPointerOver"] = Tokens.Brushes.Ink;
        SetButtonResources(Resources, Tokens.Brushes.Panel, Tokens.Brushes.Ink);
        foreach (var suffix in new[] { "", "PointerOver", "Pressed", "Disabled" })
        {
            Resources["AccentButtonBackground" + suffix] = suffix == "Disabled" ? Tokens.Brushes.Cap : Tokens.Brushes.Accent;
            Resources["AccentButtonForeground" + suffix] = suffix == "Disabled" ? Tokens.Brushes.Muted : Tokens.Brushes.AccentInk;
            Resources["AccentButtonBorderBrush" + suffix] = Avalonia.Media.Brushes.Transparent;
        }
        Add(new Style(s => s.OfType<Window>()) { Setters =
        {
            new Setter(TemplatedControl.FontFamilyProperty, Tokens.Fonts.Grotesque),
            new Setter(TemplatedControl.FontSizeProperty, Tokens.Fonts.Body),
            new Setter(TemplatedControl.ForegroundProperty, Tokens.Brushes.Ink),
            new Setter(TemplatedControl.BackgroundProperty, Tokens.Brushes.Chassis),
        } });
        Add(new Style(s => s.OfType<Button>()) { Setters =
        {
            new Setter(TemplatedControl.FontSizeProperty, Tokens.Fonts.Control),
            new Setter(TemplatedControl.CornerRadiusProperty, new CornerRadius(Tokens.Radius.Control)),
            new Setter(TemplatedControl.PaddingProperty, new Thickness(Tokens.Space.Base, Tokens.Space.Snug)),
            new Setter(TemplatedControl.MinHeightProperty, Tokens.Size.InputHeight),
        } });
        Add(new Style(s => s.OfType<TextBox>()) { Setters =
        {
            new Setter(TemplatedControl.CornerRadiusProperty, new CornerRadius(Tokens.Radius.Field)),
            new Setter(TemplatedControl.FontSizeProperty, Tokens.Fonts.Body),
            new Setter(TemplatedControl.MinHeightProperty, Tokens.Size.InputHeight),
            new Setter(TextBox.SelectionBrushProperty, Tokens.Brushes.Accent),
            new Setter(TextBox.SelectionForegroundBrushProperty, Tokens.Brushes.AccentInk),
            new Setter(TextBox.CaretBrushProperty, Tokens.Brushes.Accent),
        } });
        Add(new Style(s => s.OfType<Button>().Class(":disabled")) { Setters =
        {
            new Setter(Visual.OpacityProperty, Tokens.Material.DisabledOpacity),
        } });
    }

    internal static void SetButtonResources(IResourceDictionary resources, IBrush background, IBrush foreground)
    {
        foreach (var suffix in new[] { "", "PointerOver", "Pressed", "Disabled" })
        {
            resources["ButtonBackground" + suffix] = suffix is "PointerOver" or "Pressed" or "Disabled" ? Tokens.Brushes.Cap : background;
            resources["ButtonForeground" + suffix] = suffix == "Disabled" ? Tokens.Brushes.Muted : foreground;
            resources["ButtonBorderBrush" + suffix] = Avalonia.Media.Brushes.Transparent;
        }
    }
}
