using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace Freehand.Cleanup;

/// <summary>Hides complete dictionary-protection blocks from an optional general-model editor.</summary>
/// <remarks>
/// This transformation does not apply dictionary rules or infer meaning. A model must
/// return every opaque identifier exactly once and in order before the original blocks
/// can be restored. Core remains responsible for its existing literal validation.
/// </remarks>
public sealed class LiteralProtectionMask
{
    private const string MarkerPrefix = "[[FREEHAND_LITERAL_";
    private const string TokenFamily = "FREEHAND_LITERAL_TOKEN_";
    private const string TokenSuffix = "_END";
    private readonly string _tokenPrefix;
    private readonly string[] _blocks;

    private LiteralProtectionMask(string maskedText, string tokenPrefix, string[] blocks)
    {
        MaskedText = maskedText;
        _tokenPrefix = tokenPrefix;
        _blocks = blocks;
    }

    /// <summary>Text containing opaque identifiers in place of complete original literal blocks.</summary>
    public string MaskedText { get; }

    /// <summary>Number of complete literal blocks hidden from the editor.</summary>
    public int Count => _blocks.Length;

    /// <summary>Parses balanced, uniquely named blocks and masks each complete block without changing surrounding text.</summary>
    /// <remarks>Identifiers use the first 32 lowercase SHA-256 hex digits of the UTF-8 input, then the zero-based block index and _END.</remarks>
    public static LiteralProtectionMask Create(string text)
    {
        ArgumentNullException.ThrowIfNull(text);
        if (text.Contains(TokenFamily, StringComparison.Ordinal))
            throw new InvalidDataException("The transcript contains a reserved cleanup literal identifier.");
        var prefix = TokenFamily + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text))).ToLowerInvariant()[..32] + "_";
        var blocks = new List<string>();
        var keys = new HashSet<string>(StringComparer.Ordinal);
        var output = new StringBuilder(text.Length);
        var scan = 0;
        var copied = 0;
        var blockStart = -1;
        string? openKey = null;
        while (true)
        {
            var start = text.IndexOf(MarkerPrefix, scan, StringComparison.Ordinal);
            if (start < 0) break;
            var bodyAt = start + MarkerPrefix.Length;
            var end = text.IndexOf("]]", bodyAt, StringComparison.Ordinal);
            if (end < 0) throw new InvalidDataException("A cleanup literal marker is incomplete.");
            var body = text.AsSpan(bodyAt, end - bodyAt);
            var opening = body.EndsWith("_START", StringComparison.Ordinal);
            if (!opening && !body.EndsWith("_END", StringComparison.Ordinal))
                throw new InvalidDataException("A cleanup literal marker is malformed.");
            var key = body[..^(opening ? 6 : 4)];
            if (!IsMarkerKey(key)) throw new InvalidDataException("A cleanup literal marker identifier is invalid.");
            if (opening)
            {
                if (openKey is not null || !keys.Add(key.ToString()))
                    throw new InvalidDataException("Cleanup literal blocks must be unnested and uniquely named.");
                openKey = key.ToString();
                blockStart = start;
            }
            else
            {
                if (openKey is null || !key.Equals(openKey.AsSpan(), StringComparison.Ordinal))
                    throw new InvalidDataException("Cleanup literal blocks are unmatched or out of order.");
                output.Append(text, copied, blockStart - copied);
                output.Append(prefix).Append(blocks.Count.ToString(CultureInfo.InvariantCulture)).Append(TokenSuffix);
                var after = end + 2;
                blocks.Add(text.Substring(blockStart, after - blockStart));
                copied = after;
                openKey = null;
            }
            scan = end + 2;
        }
        if (openKey is not null) throw new InvalidDataException("A cleanup literal block is incomplete.");
        output.Append(text, copied, text.Length - copied);
        return new(output.ToString(), prefix, blocks.ToArray());
    }

    /// <summary>Restores exact original blocks only when all identifiers survive once and in their original order.</summary>
    /// <exception cref="InvalidDataException">The edited text changed, lost, duplicated, reordered or introduced a protected identifier.</exception>
    public string Restore(string editedText)
    {
        ArgumentNullException.ThrowIfNull(editedText);
        if (editedText.Contains(MarkerPrefix, StringComparison.Ordinal))
            throw new InvalidDataException("Cleanup returned unexpected literal-marker framing.");
        var output = new StringBuilder(editedText.Length);
        var copied = 0;
        var expected = 0;
        while (true)
        {
            var start = editedText.IndexOf(TokenFamily, copied, StringComparison.Ordinal);
            if (start < 0) break;
            if (!editedText.AsSpan(start).StartsWith(_tokenPrefix, StringComparison.Ordinal))
                throw new InvalidDataException("Cleanup returned an unknown literal identifier.");
            var digitsAt = start + _tokenPrefix.Length;
            var end = digitsAt;
            while (end < editedText.Length && char.IsAsciiDigit(editedText[end])) end++;
            var digits = editedText.AsSpan(digitsAt, end - digitsAt);
            if (digits.IsEmpty || digits.Length > 1 && digits[0] == '0'
                || !int.TryParse(digits, NumberStyles.None, CultureInfo.InvariantCulture, out var index)
                || !editedText.AsSpan(end).StartsWith(TokenSuffix, StringComparison.Ordinal)
                || index != expected || index >= _blocks.Length)
                throw new InvalidDataException("Cleanup changed the protected literal identifiers or their order.");
            output.Append(editedText, copied, start - copied).Append(_blocks[index]);
            copied = end + TokenSuffix.Length;
            expected++;
        }
        if (expected != _blocks.Length) throw new InvalidDataException("Cleanup removed a protected literal identifier.");
        output.Append(editedText, copied, editedText.Length - copied);
        return output.ToString();
    }

    private static bool IsMarkerKey(ReadOnlySpan<char> key)
    {
        var separator = key.IndexOf('_');
        if (separator < 0) return !key.IsEmpty && IsHex(key);
        if (separator != 32 || !IsHex(key[..separator]) || separator == key.Length - 1) return false;
        foreach (var character in key[(separator + 1)..]) if (!char.IsAsciiDigit(character)) return false;
        return true;
    }

    private static bool IsHex(ReadOnlySpan<char> text)
    {
        foreach (var character in text) if (!char.IsAsciiHexDigit(character)) return false;
        return true;
    }
}
