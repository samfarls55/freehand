using System.Globalization;
using System.Text.RegularExpressions;
using Freehand.Dictionary;

namespace Freehand.Core;

/// <summary>Conservative English number formatting without another inference model.</summary>
internal static partial class EnglishTextNormalizer
{
    private const string NumberWord = "zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|and|point|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|nineteenth|twentieth|thirtieth|fortieth|fiftieth|sixtieth|seventieth|eightieth|ninetieth|hundredth|thousandth|millionth";
    private const string SpokenNumber = @"(?!(?:and|point)\b)(?:" + NumberWord + @")(?:[ -]+(?:" + NumberWord + @"))*";
    private const string Unit = @"dollars?|cents?|percent|per\s+cent";
    private static readonly string[] Small = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"];
    private static readonly string[] Tens = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];

    // URL/path characters prevent matching number words embedded in technical text.
    [GeneratedRegex(@"(?<![\p{L}\p{N}_/\\$:.-])(?<number>(?:minus\s+)?" + SpokenNumber + @")(?:\s+(?<unit>" + Unit + @")(?:\s+(?<tail>" + SpokenNumber + @"))?)?(?![\p{L}\p{N}_/\\-]|\.[\p{L}\p{N}_])|(?<![\p{L}\p{N}_/\\$:.-])(?<number>-?\d+(?:,\d{3})*(?:\.\d+)?)(?:\s+(?<unit>" + Unit + @"))(?![\p{L}\p{N}_/\\-])", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant, 100)]
    private static partial Regex Numbers();

    internal static string Normalize(string text, IReadOnlyList<AppliedCorrection> corrections, IReadOnlyList<DictionaryEntry>? entries = null)
    {
        // Protect literal replacement outputs before formatting anything else.
        // Protecting additional identical occurrences is intentionally conservative.
        var spans = new List<(int Start, int End)>();
        foreach (var value in corrections.Select(c => c.To).Where(v => v.Length > 0).Distinct(StringComparer.Ordinal))
            for (var at = text.IndexOf(value, StringComparison.Ordinal); at >= 0; at = text.IndexOf(value, at + value.Length, StringComparison.Ordinal))
                spans.Add((at, at + value.Length));
        foreach (var entry in entries ?? [])
            if (entry.IsEnabled && entry.Kind == EntryKind.Term && entry.Write.Length > 0)
                for (var at = text.IndexOf(entry.Write, StringComparison.OrdinalIgnoreCase); at >= 0; at = text.IndexOf(entry.Write, at + entry.Write.Length, StringComparison.OrdinalIgnoreCase))
                    spans.Add((at, at + entry.Write.Length));
        try
        {
            return Numbers().Replace(text, match => spans.Any(span => match.Index < span.End && match.Index + match.Length > span.Start)
                ? match.Value : Format(match));
        }
        catch (RegexMatchTimeoutException) { return text; }
    }

    private static string Format(Match match)
    {
        var number = match.Groups["number"].Value;
        var unit = match.Groups["unit"].Value.ToLowerInvariant();
        // An amount such as "five dollars fifty" needs a richer grammar. Keep
        // the complete phrase rather than formatting just part of it.
        if (match.Groups["tail"].Success) return match.Value;
        var negative = number.StartsWith("minus ", StringComparison.OrdinalIgnoreCase) || number.StartsWith('-');
        var unsigned = number.StartsWith("minus ", StringComparison.OrdinalIgnoreCase) ? number[6..] : number.TrimStart('-');
        decimal amount;
        var decimalPlaces = 0;
        if (char.IsDigit(unsigned[0]))
        {
            if (!decimal.TryParse(unsigned, NumberStyles.AllowThousands | NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture, out amount)) return match.Value;
            var dot = unsigned.IndexOf('.');
            if (dot >= 0) decimalPlaces = unsigned.Length - dot - 1;
        }
        else
        {
            var words = unsigned.ToLowerInvariant().Split([' ', '-'], StringSplitOptions.RemoveEmptyEntries);
            var point = Array.IndexOf(words, "point");
            var integerWords = point < 0 ? words.AsSpan() : words.AsSpan(0, point);
            if (!TryInteger(integerWords, out var integer)) return match.Value;
            amount = integer;
            if (point >= 0)
            {
                var decimals = words.AsSpan(point + 1);
                if (decimals.Length is < 1 or > 6) return match.Value;
                decimal divisor = 10;
                foreach (var word in decimals)
                {
                    var digit = Array.IndexOf(Small, word);
                    if (digit is < 0 or > 9) return match.Value;
                    amount += digit / divisor; divisor *= 10;
                }
                decimalPlaces = decimals.Length;
            }
            // Preserve small standalone words in ordinary prose, such as "one way".
            if (unit.Length == 0 && integerWords.Length == 1 && integer < 10 && point < 0) return match.Value;
        }
        if (decimalPlaces > 6) return match.Value;
        if (unit is "cent" or "cents") { amount /= 100; decimalPlaces = Math.Max(2, decimalPlaces + 2); }
        var formatted = amount.ToString("N" + decimalPlaces.ToString(CultureInfo.InvariantCulture), CultureInfo.InvariantCulture);
        var sign = negative ? "-" : string.Empty;
        return unit switch
        {
            "dollar" or "dollars" or "cent" or "cents" => sign + "$" + formatted,
            "percent" or "per cent" => sign + formatted + "%",
            _ => sign + formatted,
        };
    }

    private static bool TryInteger(ReadOnlySpan<string> words, out long value)
    {
        value = 0;
        var start = 0;
        long previousScale = long.MaxValue;
        for (var i = 0; i < words.Length; i++)
        {
            var scale = words[i] switch { "million" => 1_000_000, "thousand" => 1_000, _ => 0 };
            if (scale == 0) continue;
            if (scale >= previousScale || !TryGroup(words[start..i], out var group) || group == 0) return false;
            value += group * scale; previousScale = scale; start = i + 1;
        }
        if (start == words.Length) return start > 0;
        var tail = words[start..];
        if (start > 0 && tail[0] == "and") tail = tail[1..];
        if (!TryGroup(tail, out var remainder)) return false;
        value += remainder;
        return value <= 999_999_999;
    }

    private static bool TryGroup(ReadOnlySpan<string> words, out int value)
    {
        value = 0;
        if (words.Length == 0) return false;
        if (words.Length >= 2 && words[1] == "hundred")
        {
            var hundreds = Array.IndexOf(Small, words[0]);
            if (hundreds is < 1 or > 9) return false;
            value = hundreds * 100; words = words[2..];
            if (words.Length == 0) return true;
            if (words[0] == "and") words = words[1..];
        }
        if (words.Length is < 1 or > 2) return false;
        var small = Array.IndexOf(Small, words[0]);
        if (small >= 0) { if (words.Length != 1) return false; value += small; return true; }
        var tens = Array.IndexOf(Tens, words[0]);
        if (tens < 0) return false;
        value += (tens + 2) * 10;
        if (words.Length == 1) return true;
        var ones = Array.IndexOf(Small, words[1]);
        if (ones is < 1 or > 9) return false;
        value += ones;
        return true;
    }
}
