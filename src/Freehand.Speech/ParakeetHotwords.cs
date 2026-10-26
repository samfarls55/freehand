using System.Security.Cryptography;
using System.Text;

namespace Freehand.Speech;

internal sealed class ParakeetHotwords
{
    internal const string VocabularyFile = "parakeet-110m.bpe.vocab";
    private const string VocabularyHash = "1BB9B52A1D2C3A6C6A4D6E9256A3152B78E0F1F4CDD32F235E9597436313E552";
    private readonly HashSet<char> _characters = [];

    internal ParakeetHotwords(string path)
    {
        var bytes = File.ReadAllBytes(path);
        if (!Convert.ToHexString(SHA256.HashData(bytes)).Equals(VocabularyHash, StringComparison.Ordinal))
            throw new InvalidDataException("Damaged hotword vocabulary");
        foreach (var line in Encoding.UTF8.GetString(bytes).Split('\n', StringSplitOptions.RemoveEmptyEntries))
        {
            var piece = line.Split('\t')[0];
            if (piece.StartsWith('<')) continue;
            foreach (var character in piece) if (character != '▁') _characters.Add(character);
        }
    }

    internal string Format(IReadOnlyList<string> phrases)
    {
        var words = new List<string>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var phrase in phrases.Take(WorkerProtocol.MaxBiasPhrases))
        {
            // '/' separates phrases and ':' introduces native score syntax. Never
            // interpret dictionary text as that syntax, or feed unknown characters.
            if (string.IsNullOrWhiteSpace(phrase) || phrase.Length > WorkerProtocol.MaxBiasPhraseLength
                || phrase.Any(c => c is '/' or ':' || char.IsControl(c) || (!char.IsWhiteSpace(c) && !_characters.Contains(c)))) continue;
            var normalized = string.Join(' ', phrase.Normalize(NormalizationForm.FormC).Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));
            if (seen.Add(normalized)) words.Add(normalized);
            var lowercase = normalized.ToLowerInvariant();
            if (lowercase.All(c => c == ' ' || _characters.Contains(c)) && seen.Add(lowercase)) words.Add(lowercase);
        }
        return string.Join('/', words);
    }
}
