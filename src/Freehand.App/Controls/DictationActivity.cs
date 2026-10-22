using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using Freehand.App.Design;
using Freehand.Core;

namespace Freehand.App.Controls;

internal sealed class DictationActivity : Control
{
    private readonly double[] _levels = new double[Tokens.Material.StatusBarCount];
    private bool _recording;
    private int _dot;

    internal DictationActivity()
    {
        Width = Tokens.Material.StatusBarCount * Tokens.Material.StatusBarWidth
            + (Tokens.Material.StatusBarCount - 1) * Tokens.Material.StatusBarGap;
        Height = Tokens.Material.StatusActivityHeight;
        VerticalAlignment = Avalonia.Layout.VerticalAlignment.Center;
    }

    internal void Update(DictationState state, float level)
    {
        var recording = state == DictationState.Recording;
        if (_recording != recording) { Array.Clear(_levels); _dot = 0; }
        _recording = recording;
        if (recording)
        {
            Array.Copy(_levels, 1, _levels, 0, _levels.Length - 1);
            _levels[^1] = Math.Clamp(Math.Sqrt(Math.Clamp(level, 0, 1)) * Tokens.Material.StatusLevelGain, 0, 1);
        }
        InvalidateVisual();
    }

    internal void Advance()
    {
        _dot = (_dot + 1) % Tokens.Material.StatusDotCount;
        InvalidateVisual();
    }

    public override void Render(DrawingContext context)
    {
        if (_recording)
        {
            for (var i = 0; i < _levels.Length; i++)
            {
                var height = Tokens.Material.StatusBarMinimum
                    + _levels[i] * (Tokens.Material.StatusActivityHeight - Tokens.Material.StatusBarMinimum);
                var bar = new Rect(i * (Tokens.Material.StatusBarWidth + Tokens.Material.StatusBarGap),
                    (Bounds.Height - height) / 2, Tokens.Material.StatusBarWidth, height);
                context.DrawRectangle(Tokens.Brushes.InkOnDeck, null, new RoundedRect(bar, Tokens.Radius.Chip));
            }
            return;
        }
        var pitch = Width / Tokens.Material.StatusDotCount;
        var radius = Tokens.Material.StatusDotSize / 2;
        for (var i = 0; i < Tokens.Material.StatusDotCount; i++)
        {
            var brush = new SolidColorBrush(Tokens.Colors.Accent, i == _dot ? 1 : Tokens.Material.StatusDimOpacity);
            context.DrawEllipse(brush, null, new Point(pitch * (i + 0.5), Bounds.Height / 2), radius, radius);
        }
    }
}
