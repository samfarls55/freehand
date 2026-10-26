using System.Text.Json;
using Freehand.Core;
using Freehand.Dictionary;
using Shouldly;
using Xunit;

namespace Freehand.CoreTests;

public sealed class TextNormalizationTests
{
    [Fact]
    public void Formatting_matches_the_shared_examples()
    {
        using var vectors = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "text-normalization-test-vectors.json")));
        foreach (var vector in vectors.RootElement.GetProperty("cases").EnumerateArray())
        {
            var input = vector.GetProperty("input").GetString()!;
            EnglishTextNormalizer.Normalize(input, []).ShouldBe(vector.GetProperty("expected").GetString(), input);
        }
    }

    [Fact]
    public void Explicit_replacements_remain_literal_while_other_text_is_formatted()
    {
        var corrector = new DictionaryCorrector([DictionaryEntry.Correction("my price", "twenty five dollars ")]);
        var (text, applied) = corrector.Apply("my price and fifty dollars.");
        EnglishTextNormalizer.Normalize(text, applied).ShouldBe("twenty five dollars  and $50.");
    }

    [Fact]
    public void A_literal_replacement_inside_a_number_phrase_protects_the_entire_phrase()
    {
        EnglishTextNormalizer.Normalize("twenty five dollars", [new AppliedCorrection("target", "five", 1)])
            .ShouldBe("twenty five dollars");
        EnglishTextNormalizer.Normalize("Twenty Five costs fifty dollars.", [], [DictionaryEntry.Term("twenty five")])
            .ShouldBe("Twenty Five costs $50.");
    }
}
