using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using Freehand.App.Design;

namespace Freehand.App.Controls;

/// <summary>A flat status dot, paired with text that names the state.</summary>
public sealed class Lamp : Control
{
    /// <summary>Whether the status is active.</summary>
    public static readonly StyledProperty<bool> IsLitProperty = AvaloniaProperty.Register<Lamp, bool>(nameof(IsLit));
    /// <summary>Status color.</summary>
    public static readonly StyledProperty<Color> LampColorProperty = AvaloniaProperty.Register<Lamp, Color>(nameof(LampColor), Tokens.Colors.Record);
    /// <inheritdoc cref="IsLitProperty"/>
    public bool IsLit { get => GetValue(IsLitProperty); set => SetValue(IsLitProperty, value); }
    /// <inheritdoc cref="LampColorProperty"/>
    public Color LampColor { get => GetValue(LampColorProperty); set => SetValue(LampColorProperty, value); }
    static Lamp() => AffectsRender<Lamp>(IsLitProperty, LampColorProperty);
    /// <summary>Creates a status dot.</summary>
    public Lamp() { Width = Tokens.Material.LampSize; Height = Tokens.Material.LampSize; }
    /// <inheritdoc />
    public override void Render(DrawingContext context) => context.DrawEllipse(
        new SolidColorBrush(IsLit ? LampColor : Tokens.Colors.InkSecondary), null,
        new Point(Bounds.Width / 2, Bounds.Height / 2), Bounds.Width / 2, Bounds.Height / 2);
}
