using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace Freehand.Cleanup;

/// <summary>Protects dictionary blocks and explicitly selected quoted text with compact specialist identifiers.</summary>
/// <remarks>Restoration validates every identifier before returning any text. General models retain their existing literal protocol.</remarks>
public sealed class SpecialistLiteralMask
{
    private const string Family = "FHX_";
    private const string LegacyFamily = "FREEHAND_LITERAL_TOKEN_";
    private readonly LiteralProtectionMask _dictionary;
    private readonly string[] _tokens;
    private readonly string[] _payloads;
    private readonly string? _terminalQuoteToken;

    private SpecialistLiteralMask(string maskedText, LiteralProtectionMask dictionary, string[] tokens, string[] payloads,
        string? terminalQuoteToken)
    {
        MaskedText = maskedText;
        _dictionary = dictionary;
        _tokens = tokens;
        _payloads = payloads;
        _terminalQuoteToken = terminalQuoteToken;
    }

    /// <summary>The complete transcript with exact literal spans replaced by short, distinct identifiers.</summary>
    public string MaskedText { get; }

    /// <summary>Creates a deterministic mask without normalizing, editing or interpreting literal contents.</summary>
    /// <param name="text">Complete pre-cleanup transcript.</param>
    /// <param name="removeAddedQuotePeriod">Whether to remove one model-added terminal period after an already punctuated final quote; false replays protocol v2.</param>
    public static SpecialistLiteralMask Create(string text, bool removeAddedQuotePeriod = true) =>
        CreateCore(text, removeAddedQuotePeriod, SpecialistLiteralProtocol.CompactV3);

    /// <summary>Creates an explicitly versioned mask; legacy callers retain their original overload and behavior.</summary>
    /// <param name="text">Complete pre-cleanup transcript.</param>
    /// <param name="protocol">Opt-in v4 also protects balanced single quotes and rejects ambiguous quote boundaries.</param>
    public static SpecialistLiteralMask Create(string text, SpecialistLiteralProtocol protocol) => CreateCore(text, true, protocol);

    private static SpecialistLiteralMask CreateCore(string text, bool removeAddedQuotePeriod, SpecialistLiteralProtocol protocol)
    {
        ArgumentNullException.ThrowIfNull(text);
        if (!Enum.IsDefined(protocol)) throw new ArgumentOutOfRangeException(nameof(protocol));
        if (protocol == SpecialistLiteralProtocol.CompactV4) ValidateUnicode(text);
        if (text.Contains(Family, StringComparison.Ordinal))
            throw new InvalidDataException("The transcript contains a reserved specialist literal identifier.");
        var dictionary = LiteralProtectionMask.Create(text);
        var source = dictionary.MaskedText;
        var quotes = protocol == SpecialistLiteralProtocol.CompactV4 ? QuoteSpansV4(source) : QuoteSpans(source);
        var tokens = new List<string>();
        var payloads = new List<string>();
        var known = new HashSet<string>(StringComparer.Ordinal);
        var output = new StringBuilder(source.Length);
        var sourceEnd = source.Length;
        while (sourceEnd > 0 && char.IsWhiteSpace(source[sourceEnd - 1])) sourceEnd--;
        string? terminalQuoteToken = null;
        var at = 0;
        while (at < source.Length)
        {
            var end = at;
            var quoted = quotes.TryGetValue(at, out var quoteEnd);
            if (quoted) end = quoteEnd;
            else if (source.AsSpan(at).StartsWith(LegacyFamily, StringComparison.Ordinal))
            {
                // The first adapter created these tokens and rejected their family
                // in the original input, so this suffix belongs to a complete block.
                var suffix = source.IndexOf("_END", at + LegacyFamily.Length, StringComparison.Ordinal);
                if (suffix < 0) throw new InvalidDataException("The dictionary literal token is incomplete.");
                end = suffix + "_END".Length;
            }
            if (end == at) { output.Append(source[at++]); continue; }
            var payload = source[at..end];
            var ordinal = tokens.Count.ToString(CultureInfo.InvariantCulture);
            var nonce = 0;
            string token;
            do
            {
                var seed = ordinal + ":" + nonce.ToString(CultureInfo.InvariantCulture) + ":" + payload;
                token = Family + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(seed))).ToLowerInvariant()[..8];
                nonce++;
            }
            while (!known.Add(token));
            tokens.Add(token); payloads.Add(payload); output.Append(token); at = end;
            if (removeAddedQuotePeriod && quoted && end == sourceEnd && payload.Length >= 2 && payload[^2] is '.' or '?' or '!'
                && !(payload[^2] == '.' && payload.Length >= 3 && payload[^3] == '.'))
                terminalQuoteToken = token;
        }
        return new(output.ToString(), dictionary, tokens.ToArray(), payloads.ToArray(), terminalQuoteToken);
    }

    /// <summary>Restores exact bytes only after every short identifier survives once and in source order.</summary>
    /// <exception cref="InvalidDataException">An identifier was changed, lost, duplicated, reordered or introduced.</exception>
    public string Restore(string editedText)
    {
        ArgumentNullException.ThrowIfNull(editedText);
        if (_terminalQuoteToken is not null)
        {
            var end = editedText.Length;
            while (end > 0 && char.IsWhiteSpace(editedText[end - 1])) end--;
            var tokenAt = end - 1 - _terminalQuoteToken.Length;
            // The original ended at the quote. Remove only a single immediate
            // outside full stop invented after its final opaque identifier.
            if (tokenAt >= 0 && editedText[end - 1] == '.'
                && editedText.AsSpan(tokenAt, _terminalQuoteToken.Length).SequenceEqual(_terminalQuoteToken))
                editedText = editedText.Remove(end - 1, 1);
        }
        var output = new StringBuilder(editedText.Length);
        var copied = 0;
        var expected = 0;
        while (true)
        {
            var start = editedText.IndexOf(Family, copied, StringComparison.Ordinal);
            if (start < 0) break;
            if (expected >= _tokens.Length || !editedText.AsSpan(start).StartsWith(_tokens[expected], StringComparison.Ordinal))
                throw new InvalidDataException("Cleanup changed the specialist literal identifiers or their order.");
            output.Append(editedText, copied, start - copied).Append(_payloads[expected]);
            copied = start + _tokens[expected].Length;
            expected++;
        }
        if (expected != _tokens.Length) throw new InvalidDataException("Cleanup removed a specialist literal identifier.");
        output.Append(editedText, copied, editedText.Length - copied);
        return _dictionary.Restore(output.ToString());
    }

    private static Dictionary<int, int> QuoteSpans(string text)
    {
        var spans = new Dictionary<int, int>();
        var opening = -1;
        var closing = '\0';
        for (var at = 0; at < text.Length; at++)
        {
            var character = text[at];
            if (character is not ('"' or '“' or '”') || IsEscaped(text, at)) continue;
            if (opening >= 0)
            {
                if (character != closing) continue;
                spans.Add(opening, at + 1);
                opening = -1;
            }
            else if (character is '"' or '“')
            {
                opening = at;
                closing = character == '"' ? '"' : '”';
            }
        }
        return spans;
    }

    private static void ValidateUnicode(string text)
    {
        for (var at = 0; at < text.Length;)
        {
            if (!Rune.TryGetRuneAt(text, at, out var rune))
                throw new InvalidDataException("Specialist literal v4 requires valid Unicode scalar values.");
            at += rune.Utf16SequenceLength;
        }
    }

    private static Dictionary<int, int> QuoteSpansV4(string text)
    {
        var spans = new Dictionary<int, int>();
        var closing = new List<char>();
        var opening = -1;
        var pairedSingleFamilies = 0;
        var barePossessiveFamilies = 0;
        var leadingElisionFamilies = 0;
        for (var at = 0; at < text.Length; at++)
        {
            var character = text[at];
            if (character is not ('"' or '“' or '”' or '\'' or '‘' or '’') || IsEscaped(text, at)) continue;
            var single = character is '\'' or '‘' or '’';
            var before = WordBefore(text, at);
            var after = WordAt(text, at + 1);
            if (single && before && after) continue; // don't, we're, it's, l’esprit
            if ((character is '\'' or '’') && !before && IsLeadingElision(text, at))
            {
                if (closing.Count == 0) leadingElisionFamilies |= character == '\'' ? 1 : 2;
                continue;
            }

            if (closing.Count > 0 && character == closing[^1])
            {
                // Identical straight delimiters can nest only at an unmistakable
                // opening word boundary. An end after padding/punctuation closes.
                if ((character is '"' or '\'') && !before && after)
                {
                    PushQuote(closing, character);
                    continue;
                }
                closing.RemoveAt(closing.Count - 1);
                if (single) pairedSingleFamilies |= character == '\'' ? 1 : 2;
                if (closing.Count == 0) spans.Add(opening, at + 1);
                continue;
            }
            if (character is '”' or '’')
            {
                if (character == '’' && before && !closing.Contains('’'))
                {
                    if (closing.Count == 0 && AmbiguousTerminalApostrophe(text, at)) barePossessiveFamilies |= 2;
                    continue;
                }
                throw new InvalidDataException("Specialist literal v4 found unmatched or crossing quote delimiters.");
            }
            if (character == '\'' && before)
            {
                if (closing.Count == 0 && AmbiguousTerminalApostrophe(text, at)) barePossessiveFamilies |= 1;
                continue; // James' outside a single quote never opens one.
            }
            if (closing.Count == 0) opening = at;
            PushQuote(closing, character switch { '“' => '”', '‘' => '’', _ => character });
        }
        if (closing.Count != 0 || ((pairedSingleFamilies | leadingElisionFamilies) & barePossessiveFamilies) != 0)
            throw new InvalidDataException("Specialist literal v4 found an unmatched or ambiguous quote boundary.");
        return spans;
    }

    private static void PushQuote(List<char> closing, char character)
    {
        if (closing.Count >= 64) throw new InvalidDataException("Specialist literal v4 quote nesting is too deep.");
        closing.Add(character);
    }

    private static bool IsLeadingElision(string text, int at)
    {
        var end = at + 1;
        while (WordAt(text, end)) end += Rune.GetRuneAt(text, end).Utf16SequenceLength;
        if (end < text.Length && text[end] == text[at]) return false; // 'cause' is a pair.
        var word = text.AsSpan(at + 1, end - at - 1);
        foreach (var character in word) if (character > 0x7f) return false;
        return word.Equals("cause", StringComparison.OrdinalIgnoreCase) || word.Equals("em", StringComparison.OrdinalIgnoreCase)
            || word.Equals("tis", StringComparison.OrdinalIgnoreCase);
    }

    private static bool AmbiguousTerminalApostrophe(string text, int at)
    {
        // Ordinary James' notebook has a following noun. Unquoted -in'
        // shortenings (goin', waitin') also remain speech, including at the end.
        if (at >= 2 && (text[at - 2] is 'i' or 'I') && (text[at - 1] is 'n' or 'N')) return false;
        var after = at + 1;
        while (after < text.Length && char.IsWhiteSpace(text[after])) after++;
        return !WordAt(text, after);
    }

    private static bool WordBefore(string text, int at)
    {
        if (at == 0) return false;
        at--;
        if (char.IsLowSurrogate(text[at])) at--;
        return WordAt(text, at);
    }

    private static bool WordAt(string text, int at)
    {
        if (at < 0 || at >= text.Length) return false;
        return SpecialistLiteralWordRanges.IsWord(Rune.GetRuneAt(text, at).Value);
    }

    private static bool IsEscaped(string text, int at)
    {
        var slashes = 0;
        while (at > 0 && text[--at] == '\\') slashes++;
        return (slashes & 1) != 0;
    }
}
