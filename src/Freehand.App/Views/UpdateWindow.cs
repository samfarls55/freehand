using Avalonia;
using Avalonia.Controls;
using Freehand.App.Design;
using Freehand.Core.Updates;

namespace Freehand.App.Views;

/// <summary>An update offer that leaves keyboard focus in the user's foreground app.</summary>
internal sealed class UpdateWindow : Window
{
    internal UpdateWindow(UpdateService updates)
    {
        Title = "Freehand update"; Width = 460; CanResize = false;
        SizeToContent = SizeToContent.Height; ShowActivated = false;
        Background = Tokens.Brushes.Chassis; WindowStartupLocation = WindowStartupLocation.CenterScreen;
        Content = new UpdateView(updates, Close) { Margin = new Thickness(Tokens.Space.Panel) };
    }
}
