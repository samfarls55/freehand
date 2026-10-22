using Avalonia.Media;

namespace Freehand.App.Design;

/// <summary>The approved Compact palette, typography, and native control geometry.</summary>
internal static class Tokens
{
    internal static class Colors
    {
        public static Color Chassis => Color.Parse("#1C1F20");
        public static Color Panel => Color.Parse("#232728");
        public static Color Cap => Color.Parse("#252A2A");
        public static Color Deck => Chassis;
        public static Color Seam => Color.Parse("#343A39");
        public static Color Ink => Color.Parse("#F1F3F2");
        public static Color InkSecondary => Color.Parse("#AFB6B3");
        public static Color InkOnDeck => Ink;
        public static Color Record => Color.Parse("#F45B55");
        public static Color Accent => Color.Parse("#B5C9BC");
        public static Color AccentInk => Color.Parse("#18231C");
        public static Color MeterGreen => Accent;
        public static Color MeterAmber => Color.Parse("#E3BD7B");
    }

    internal static class Brushes
    {
        public static SolidColorBrush Chassis { get; } = new(Colors.Chassis);
        public static SolidColorBrush Panel { get; } = new(Colors.Panel);
        public static SolidColorBrush Cap { get; } = new(Colors.Cap);
        public static SolidColorBrush Deck => Chassis;
        public static SolidColorBrush Seam { get; } = new(Colors.Seam);
        public static SolidColorBrush Ink { get; } = new(Colors.Ink);
        public static SolidColorBrush Muted { get; } = new(Colors.InkSecondary);
        public static SolidColorBrush InkOnDeck => Ink;
        public static SolidColorBrush Accent { get; } = new(Colors.Accent);
        public static SolidColorBrush AccentInk { get; } = new(Colors.AccentInk);
        public static SolidColorBrush Record { get; } = new(Colors.Record);
        public static SolidColorBrush Attention { get; } = new(Colors.MeterAmber);
    }

    internal static class Fonts
    {
        public static FontFamily Grotesque { get; } = new("Segoe UI Variable, Segoe UI, sans-serif");
        public static FontFamily Mono { get; } = new("Cascadia Mono, Consolas, monospace");
        public const double Label = 13;
        public const double Control = 14;
        public const double Body = 15;
        public const double Transcript = 16;
        public const double TranscriptLine = 27;
        public const double Section = 17;
        public const double Title = 30;
    }

    internal static class Space
    {
        public const double Hair = 2;
        public const double Tight = 4;
        public const double Snug = 8;
        public const double Base = 12;
        public const double Roomy = 16;
        public const double Wide = 24;
        public const double Panel = 32;
        public const double Gutter = 44;
    }

    internal static class Radius
    {
        public const double Chip = 2;
        public const double Field = 6;
        public const double Control = 7;
        public const double Panel = 8;
        public const double Status = Size.StatusHeight / 2;
    }

    internal static class Border { public const double Hairline = 1; }

    internal static class Material
    {
        public const double LampSize = 7;
        public const int StatusBarCount = 5;
        public const double StatusBarWidth = 3;
        public const double StatusBarGap = 3;
        public const double StatusActivityHeight = 20;
        public const double StatusBarMinimum = 4;
        public const double StatusLevelGain = 3;
        public const int StatusDotCount = 3;
        public const double StatusDotSize = 4;
        public const double StatusDimOpacity = 0.35;
        public const double DisabledOpacity = 0.45;
        public const double IconStroke = 1.5;
        public const double NavigationUnderline = 3;
    }

    internal static class Size
    {
        public const double WindowWidth = 880;
        public const double WindowHeight = 700;
        public const double MinimumWidth = 720;
        public const double MinimumHeight = 520;
        public const double InputHeight = 38;
        public const double BrandMark = 24;
        public const double StatusWidth = 208;
        public const double StatusHeight = 44;
        public const double StatusAttentionWidth = 288;
        public const double TranscriptHeight = 100;
        public const double QuitDialogWidth = 440;
    }

    internal static class Motion
    {
        public static TimeSpan StatusActivity { get; } = TimeSpan.FromMilliseconds(180);
        public static TimeSpan StatusAttention { get; } = TimeSpan.FromSeconds(3);
    }
}
