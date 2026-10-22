using Avalonia;
using Avalonia.Controls;
using Freehand.App.Design;
using Freehand.Core;

namespace Freehand.App.Views;

/// <summary>Tray settings dialog, sharing the same controls as the main Settings tab.</summary>
public sealed class SettingsWindow : Window
{
    /// <summary>Builds the tray settings window.</summary>
    public SettingsWindow(AppSettings settings, Composition? composition = null)
    {
        Title = "Freehand Settings"; Width = 640; Height = 700;
        MinWidth = 540; MinHeight = Tokens.Size.MinimumHeight;
        Background = Tokens.Brushes.Chassis; WindowStartupLocation = WindowStartupLocation.CenterOwner;
        Content = new SettingsView(settings, composition) { Margin = new Thickness(Tokens.Space.Panel, 0, Tokens.Space.Panel, Tokens.Space.Roomy) };
    }
}
