using Shouldly;
using Xunit;

namespace Freehand.Cleanup.Tests;

public sealed class SpecialistLiteralMaskTests
{
    [Fact]
    public void Dictionary_vector_matches_the_independent_mirror_and_restores_exact_bytes()
    {
        const string text = "Before [[FREEHAND_LITERAL_01_START]]  Acme\tLabs  [[FREEHAND_LITERAL_01_END]] after.";
        var mask = SpecialistLiteralMask.Create(text);

        mask.MaskedText.ShouldBe("Before FHX_45a27cf4 after.");
        mask.Restore(mask.MaskedText).ShouldBe(text);
        mask.MaskedText.ShouldNotContain("Acme");
        mask.MaskedText.ShouldNotContain("FREEHAND_LITERAL_TOKEN_");
    }

    [Fact]
    public void Straight_and_curly_quoted_vectors_match_the_independent_mirror()
    {
        const string text = "Keep \"very, very small\" and “like, like” exactly.";
        var mask = SpecialistLiteralMask.Create(text);

        mask.MaskedText.ShouldBe("Keep FHX_8cd46b56 and FHX_2e5722a9 exactly.");
        mask.Restore(mask.MaskedText).ShouldBe(text);
    }

    [Fact]
    public void Multiple_distinct_and_repeated_payloads_get_short_unique_deterministic_identifiers()
    {
        const string text = "\"same\" \"same\" “different”";
        var mask = SpecialistLiteralMask.Create(text);
        var tokens = mask.MaskedText.Split(' ');

        tokens.Length.ShouldBe(3);
        tokens.Distinct(StringComparer.Ordinal).Count().ShouldBe(3);
        foreach (var token in tokens) { token.Length.ShouldBe(12); token.ShouldStartWith("FHX_"); }
        SpecialistLiteralMask.Create(text).MaskedText.ShouldBe(mask.MaskedText);
        mask.Restore(mask.MaskedText).ShouldBe(text);
    }

    [Fact]
    public void A_quoted_dictionary_block_and_unicode_whitespace_are_preserved_through_both_adapters()
    {
        const string text = "Uh, keep \"[[FREEHAND_LITERAL_a_START]]  café\tΔ🙂\r\n  [[FREEHAND_LITERAL_a_END]]\" and “like”.";
        var mask = SpecialistLiteralMask.Create(text);
        var edited = mask.MaskedText.Replace("Uh, keep", "Keep", StringComparison.Ordinal);

        mask.Restore(edited).ShouldBe(text.Replace("Uh, keep", "Keep", StringComparison.Ordinal));
        mask.MaskedText.ShouldNotContain("café");
        mask.MaskedText.ShouldNotContain("like");
        mask.MaskedText.ShouldNotContain("FREEHAND_LITERAL_TOKEN_");
    }

    [Theory]
    [InlineData("I don't think we should change contractions.")]
    [InlineData("Keep unquoted like and um ordinary.")]
    [InlineData("An unmatched \"opening remains ordinary.")]
    [InlineData("An unmatched “opening remains ordinary.")]
    [InlineData("An escaped \\\"quote\\\" remains ordinary.")]
    [InlineData("An unmatched \"outer “pair” remains ordinary.")]
    public void Unquoted_contractions_escaped_or_unbalanced_quotes_remain_ordinary(string text)
    {
        var mask = SpecialistLiteralMask.Create(text);

        mask.MaskedText.ShouldBe(text);
        mask.Restore(text).ShouldBe(text);
    }

    [Fact]
    public void Escaped_inner_quotes_do_not_end_the_protected_outer_quote()
    {
        const string text = "Keep \"say \\\"um\\\" here\" exactly.";
        var mask = SpecialistLiteralMask.Create(text);

        mask.MaskedText.ShouldNotContain("say");
        mask.MaskedText.ShouldNotContain("um");
        mask.Restore(mask.MaskedText).ShouldBe(text);
    }

    [Fact]
    public void An_even_backslash_count_allows_the_closing_quote()
    {
        const string text = """Keep "C:\\" exactly.""";
        var mask = SpecialistLiteralMask.Create(text);

        mask.MaskedText.ShouldNotContain("C:");
        mask.Restore(mask.MaskedText).ShouldBe(text);
    }

    [Fact]
    public void Missing_duplicated_reordered_changed_and_unknown_identifiers_never_return_partial_restoration()
    {
        var mask = SpecialistLiteralMask.Create("\"first\" \"second\"");
        var tokens = mask.MaskedText.Split(' ');
        string[] invalid =
        [
            tokens[0], tokens[0] + " " + tokens[0] + " " + tokens[1], tokens[1] + " " + tokens[0],
            "FHX_deadbeef " + tokens[1], mask.MaskedText + " FHX_unknown", mask.MaskedText + " " + tokens[1],
        ];

        foreach (var edited in invalid) Should.Throw<InvalidDataException>(() => mask.Restore(edited));
    }

    [Theory]
    [InlineData("FHX_ordinary")]
    [InlineData("\"FHX_ordinary\"")]
    [InlineData("[[FREEHAND_LITERAL_01_START]]FHX_ordinary[[FREEHAND_LITERAL_01_END]]")]
    public void Reserved_family_collisions_are_rejected_before_model_inference(string text) =>
        Should.Throw<InvalidDataException>(() => SpecialistLiteralMask.Create(text));

    [Fact]
    public void General_literal_protocol_keeps_its_existing_quoted_text_behavior()
    {
        const string text = "Keep \"like\" exactly.";

        LiteralProtectionMask.Create(text).MaskedText.ShouldBe(text);
        SpecialistLiteralMask.Create(text).MaskedText.ShouldNotBe(text);
    }

    [Theory]
    [InlineData("The message says \"Do not publish.\"")]
    [InlineData("Keep “Is this ready?”")]
    [InlineData("She said \"Stop!\"\r\n  ")]
    public void Version_three_removes_only_a_new_single_period_after_an_already_punctuated_terminal_quote(string text)
    {
        var mask = SpecialistLiteralMask.Create(text);
        var end = mask.MaskedText.TrimEnd().Length;
        var edited = mask.MaskedText.Insert(end, ".");

        mask.Restore(edited).ShouldBe(text);
        SpecialistLiteralMask.Create(text, removeAddedQuotePeriod: false).Restore(edited).ShouldBe(text.Insert(text.TrimEnd().Length, "."));
    }

    [Theory]
    [InlineData("Keep \"Do not publish.\".")]
    [InlineData("Keep \"Do not publish.\"...")]
    [InlineData("Keep \"Do not publish.\" and wait.")]
    [InlineData("Keep \"no inner punctuation\"")]
    [InlineData("Keep \"Wait...\"")]
    public void Original_outside_punctuation_mid_sentence_quotes_unpunctuated_quotes_and_ellipsis_are_not_normalized(string text)
    {
        var mask = SpecialistLiteralMask.Create(text);

        mask.Restore(mask.MaskedText + ".").ShouldBe(text + ".");
    }

    [Theory]
    [InlineData("..")]
    [InlineData("...")]
    [InlineData(". Another sentence.")]
    public void Version_three_keeps_model_ellipses_or_additional_words_after_the_terminal_identifier(string suffix)
    {
        const string text = "Keep \"Already done.\"";
        var mask = SpecialistLiteralMask.Create(text);

        mask.Restore(mask.MaskedText + suffix).ShouldBe(text + suffix);
    }

    [Fact]
    public void Terminal_quote_normalization_does_not_modify_hidden_dictionary_bytes()
    {
        const string text = "Keep \"[[FREEHAND_LITERAL_01_START]]  café\tΔ\r\n  [[FREEHAND_LITERAL_01_END]] remains exact.\"";
        var mask = SpecialistLiteralMask.Create(text);

        mask.Restore(mask.MaskedText + ".").ShouldBe(text);
    }
}
