using System.Text.Json;
using Freehand.Core;
using Freehand.Dictionary;
using Shouldly;
using Xunit;

namespace Freehand.CoreTests;

public sealed class TextNormalizationTests
{
    [Fact]
    public void Cascading_corrections_preserve_every_surviving_literal_character()
    {
        var corrector = new DictionaryCorrector([
            DictionaryEntry.Correction("my price", "twenty five dollars"),
            DictionaryEntry.Correction("dollars", "USD")]);
        var (text, _, ranges) = corrector.ApplyWithProtectedRanges("my price and fifty percent.");
        EnglishTextNormalizer.Normalize(text, ranges).ShouldBe("twenty five USD and 50%.");
    }

    [Fact]
    public void Literal_ranges_follow_repeated_replacements_and_prefix_length_changes()
    {
        var corrector = new DictionaryCorrector([
            DictionaryEntry.Correction("my price", "twenty five dollars"),
            DictionaryEntry.Correction("dollars", "USD"),
            DictionaryEntry.Correction("prefix", "one hundred:")]);
        var (text, _, ranges) = corrector.ApplyWithProtectedRanges("prefix my price; my price; fifty percent.");
        EnglishTextNormalizer.Normalize(text, ranges).ShouldBe("one hundred: twenty five USD; twenty five USD; 50%.");
    }

    [Fact]
    public void Deleting_part_of_a_replacement_keeps_its_surviving_characters_protected()
    {
        var corrector = new DictionaryCorrector([
            DictionaryEntry.Correction("long price name", "twenty five dollars"),
            DictionaryEntry.Correction("five dollars", "")]);
        var (text, _, ranges) = corrector.ApplyWithProtectedRanges("long price name; fifty percent.");
        EnglishTextNormalizer.Normalize(text, ranges).ShouldBe("twenty ; 50%.");
    }

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
        var (text, _, ranges) = corrector.ApplyWithProtectedRanges("my price and fifty dollars.");
        EnglishTextNormalizer.Normalize(text, ranges).ShouldBe("twenty five dollars  and $50.");
    }

    [Fact]
    public void A_literal_replacement_inside_a_number_phrase_protects_the_entire_phrase()
    {
        EnglishTextNormalizer.Normalize("twenty five dollars", [new CorrectionRange(7, 4)])
            .ShouldBe("twenty five dollars");
        EnglishTextNormalizer.Normalize("Twenty Five costs fifty dollars.", [], [DictionaryEntry.Term("twenty five")])
            .ShouldBe("Twenty Five costs $50.");
    }
}
