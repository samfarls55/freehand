using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace Freehand.Cleanup;

/// <summary>Protects dictionary blocks and paired double-quoted text with compact specialist identifiers.</summary>
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
    public static SpecialistLiteralMask Create(string text, bool removeAddedQuotePeriod = true)
    {
        ArgumentNullException.ThrowIfNull(text);
        if (text.Contains(Family, StringComparison.Ordinal))
            throw new InvalidDataException("The transcript contains a reserved specialist literal identifier.");
        var dictionary = LiteralProtectionMask.Create(text);
        var source = dictionary.MaskedText;
        var quotes = QuoteSpans(source);
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

    private static bool IsEscaped(string text, int at)
    {
        var slashes = 0;
        while (at > 0 && text[--at] == '\\') slashes++;
        return (slashes & 1) != 0;
    }
}
