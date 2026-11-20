using Freehand.Cleanup;
using Shouldly;
using Xunit;

namespace Freehand.Cleanup.Tests;

public sealed class LiteralProtectionMaskTests
{
    [Theory]
    [InlineData("Before [[FREEHAND_LITERAL_01_START]]  Acme\tLabs  [[FREEHAND_LITERAL_01_END]] after.", "e772fedf3921e34f0f37d0bbe6231d4f")]
    [InlineData("Before [[FREEHAND_LITERAL_01_START]]  café\tΔ🙂  [[FREEHAND_LITERAL_01_END]] after.", "1584b4413f918ffffe43d6b47fd6798e")]
    public void Mask_uses_a_reproducible_utf8_digest_and_restores_literal_whitespace_exactly(string original, string digest)
    {
        var mask = LiteralProtectionMask.Create(original);

        mask.Count.ShouldBe(1);
        mask.MaskedText.ShouldBe("Before FREEHAND_LITERAL_TOKEN_" + digest + "_0_END after.");
        mask.Restore(mask.MaskedText).ShouldBe(original);
        mask.Restore(mask.MaskedText.Replace("Before", "After", StringComparison.Ordinal))
            .ShouldBe(original.Replace("Before", "After", StringComparison.Ordinal));
        LiteralProtectionMask.Create(original).MaskedText.ShouldBe(mask.MaskedText);
    }

    [Fact]
    public void Adjacent_core_blocks_with_repeated_values_keep_their_independent_identity_and_exact_bytes()
    {
        var key = new string('a', 32);
        const string value = "  v2::Thing<T>\t\r\n  value  ";
        var original = Block(key + "_0", value) + Block(key + "_1", value);
        var mask = LiteralProtectionMask.Create(original);

        mask.Count.ShouldBe(2);
        mask.MaskedText.ShouldNotContain(value);
        mask.Restore(mask.MaskedText).ShouldBe(original);
    }

    [Fact]
    public void At_least_twelve_adjacent_spans_are_unambiguous_for_indexes_one_and_ten()
    {
        var original = string.Concat(Enumerable.Range(0, 12).Select(index =>
            Block(index.ToString("x2", System.Globalization.CultureInfo.InvariantCulture), "same value")));
        var mask = LiteralProtectionMask.Create(original);

        mask.Count.ShouldBe(12);
        mask.MaskedText.ShouldContain("_1_END");
        mask.MaskedText.ShouldContain("_10_END");
        mask.MaskedText.ShouldContain("_11_END");
        mask.Restore(mask.MaskedText).ShouldBe(original);
    }

    [Theory]
    [InlineData("missing")]
    [InlineData("duplicate")]
    [InlineData("unknown-index")]
    [InlineData("leading-zero")]
    [InlineData("changed-nonce")]
    [InlineData("broken-suffix")]
    [InlineData("invented-marker")]
    public void Restoration_rejects_lost_duplicated_changed_or_invented_identifiers(string damage)
    {
        var mask = LiteralProtectionMask.Create(Block("01", "  Acme\tLabs  "));
        var token = mask.MaskedText;
        var edited = damage switch
        {
            "missing" => "A model removed the protected value.",
            "duplicate" => token + " " + token,
            "unknown-index" => token.Replace("_0_END", "_99_END", StringComparison.Ordinal),
            "leading-zero" => token.Replace("_0_END", "_00_END", StringComparison.Ordinal),
            "changed-nonce" => token.ToUpperInvariant(),
            "broken-suffix" => token.Replace("_END", "_EN", StringComparison.Ordinal),
            _ => token + " " + Block("aa", "invented"),
        };

        Should.Throw<InvalidDataException>(() => mask.Restore(edited));
    }

    [Fact]
    public void Restoration_rejects_reordering_and_unknown_extra_identifiers()
    {
        var mask = LiteralProtectionMask.Create(Block("01", "first") + " " + Block("02", "second"));
        var tokens = mask.MaskedText.Split(' ');
        Should.Throw<InvalidDataException>(() => mask.Restore(tokens[1] + " " + tokens[0]));
        Should.Throw<InvalidDataException>(() => mask.Restore(mask.MaskedText + " FREEHAND_LITERAL_TOKEN_unknown_2_END"));
    }

    [Theory]
    [InlineData("[[FREEHAND_LITERAL_01_START]]unclosed")]
    [InlineData("stray [[FREEHAND_LITERAL_01_END]]")]
    [InlineData("[[FREEHAND_LITERAL_01_START]]mismatched[[FREEHAND_LITERAL_02_END]]")]
    [InlineData("[[FREEHAND_LITERAL_01_START]][[FREEHAND_LITERAL_02_START]]nested[[FREEHAND_LITERAL_02_END]][[FREEHAND_LITERAL_01_END]]")]
    [InlineData("[[FREEHAND_LITERAL_01_START]]a[[FREEHAND_LITERAL_01_END]][[FREEHAND_LITERAL_01_START]]b[[FREEHAND_LITERAL_01_END]]")]
    [InlineData("[[FREEHAND_LITERAL_01_STOP]]")]
    [InlineData("[[FREEHAND_LITERAL_not-hex_START]]a[[FREEHAND_LITERAL_not-hex_END]]")]
    [InlineData("[[FREEHAND_LITERAL_abcd_0_START]]a[[FREEHAND_LITERAL_abcd_0_END]]")]
    [InlineData("[[FREEHAND_LITERAL_01_START")]
    public void Malformed_nested_or_ambiguous_source_blocks_are_rejected(string original)
    {
        Should.Throw<InvalidDataException>(() => LiteralProtectionMask.Create(original));
    }

    [Theory]
    [InlineData("FREEHAND_LITERAL_TOKEN_existing_0_END")]
    [InlineData("[[FREEHAND_LITERAL_01_START]]FREEHAND_LITERAL_TOKEN_existing_0_END[[FREEHAND_LITERAL_01_END]]")]
    public void Reserved_identifier_family_cannot_collide_with_source_text(string original)
    {
        Should.Throw<InvalidDataException>(() => LiteralProtectionMask.Create(original));
    }

    [Fact]
    public void Ordinary_text_remains_unchanged_and_unrelated_edits_can_be_returned()
    {
        const string original = "Uh, café <T> and </transcript> are quoted text.\n";
        var mask = LiteralProtectionMask.Create(original);
        mask.Count.ShouldBe(0);
        mask.MaskedText.ShouldBe(original);
        mask.Restore("Café <T> and </transcript> are quoted text.\n").ShouldBe("Café <T> and </transcript> are quoted text.\n");
        Should.Throw<InvalidDataException>(() => mask.Restore("FREEHAND_LITERAL_TOKEN_unknown_0_END"));
    }

    private static string Block(string key, string value) => "[[FREEHAND_LITERAL_" + key + "_START]]" + value
        + "[[FREEHAND_LITERAL_" + key + "_END]]";
}
