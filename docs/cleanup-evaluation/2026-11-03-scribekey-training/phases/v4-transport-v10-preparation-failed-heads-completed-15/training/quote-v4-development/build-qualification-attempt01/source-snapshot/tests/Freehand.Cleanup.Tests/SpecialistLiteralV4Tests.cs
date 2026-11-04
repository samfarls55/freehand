using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Shouldly;
using Xunit;

namespace Freehand.Cleanup.Tests;

public sealed class SpecialistLiteralV4Tests
{
    [Fact]
    public void Shared_scalar_and_utf8_vectors_protect_only_the_intended_complete_spans()
    {
        using var vectors = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "specialist-literal-v4-vectors.json")));
        foreach (var vector in vectors.RootElement.GetProperty("accepted").EnumerateArray())
        {
            var text = vector.GetProperty("text").GetString()!;
            var mask = SpecialistLiteralMask.Create(text, protocol: SpecialistLiteralProtocol.CompactV4);
            mask.MaskedText.ShouldBe(vector.GetProperty("masked_text").GetString(), vector.GetProperty("id").GetString());
            Hash(text).ShouldBe(vector.GetProperty("text_utf8_sha256").GetString());
            Hash(mask.MaskedText).ShouldBe(vector.GetProperty("masked_utf8_sha256").GetString());
            Encoding.UTF8.GetBytes(mask.Restore(mask.MaskedText)).ShouldBe(Encoding.UTF8.GetBytes(text));
        }
        foreach (var vector in vectors.RootElement.GetProperty("rejected").EnumerateArray())
            Should.Throw<InvalidDataException>(() => SpecialistLiteralMask.Create(vector.GetString()!, protocol: SpecialistLiteralProtocol.CompactV4));
    }

    [Fact]
    public void Version_three_and_general_defaults_do_not_start_protecting_single_quotes()
    {
        const string text = "Keep 'Uh, wait here' and ‘ready later’ exactly.";
        Func<string, bool, SpecialistLiteralMask> legacyBinarySignature = SpecialistLiteralMask.Create;
        legacyBinarySignature(text, false).MaskedText.ShouldBe(text);
        SpecialistLiteralMask.Create(text).MaskedText.ShouldBe(text);
        LiteralProtectionMask.Create(text).MaskedText.ShouldBe(text);
        SpecialistLiteralMask.Create(text, protocol: SpecialistLiteralProtocol.CompactV4).MaskedText.ShouldNotContain("Uh");
    }

    [Fact]
    public void Quotes_containing_dictionary_blocks_restore_exact_nested_payload_bytes()
    {
        const string text = "Um, keep '[[FREEHAND_LITERAL_01_START]]  café\tΔ🙂\r\n  [[FREEHAND_LITERAL_01_END]]' and ‘Uh, wait.’";
        var mask = SpecialistLiteralMask.Create(text, protocol: SpecialistLiteralProtocol.CompactV4);
        mask.MaskedText.ShouldNotContain("café");
        mask.MaskedText.ShouldNotContain("FREEHAND_LITERAL_TOKEN_");
        mask.MaskedText.ShouldNotContain("Uh");
        mask.Restore(mask.MaskedText.Replace("Um, keep", "Keep", StringComparison.Ordinal))
            .ShouldBe(text.Replace("Um, keep", "Keep", StringComparison.Ordinal));
    }

    [Fact]
    public void Lost_duplicated_reordered_or_new_tokens_reject_without_partial_restoration()
    {
        var mask = SpecialistLiteralMask.Create("'same' ‘same’", protocol: SpecialistLiteralProtocol.CompactV4);
        var tokens = mask.MaskedText.Split(' ');
        string[] invalid = [tokens[0], tokens[0] + " " + tokens[0] + " " + tokens[1], tokens[1] + " " + tokens[0], mask.MaskedText + " FHX_deadbeef"];
        foreach (var edited in invalid) Should.Throw<InvalidDataException>(() => mask.Restore(edited));
    }

    [Fact]
    public void Version_four_keeps_existing_terminal_period_rule_outside_exact_quote_bytes()
    {
        const string text = "Keep 'Do not change.'\r\n  ";
        var mask = SpecialistLiteralMask.Create(text, protocol: SpecialistLiteralProtocol.CompactV4);
        mask.Restore(mask.MaskedText.Insert(mask.MaskedText.TrimEnd().Length, ".")).ShouldBe(text);
    }

    [Theory]
    [InlineData(0xd800)]
    [InlineData(0xdfff)]
    public void Invalid_unicode_cannot_acquire_replacement_bytes(int surrogate)
    {
        var text = new string((char)surrogate, 1);
        Should.Throw<InvalidDataException>(() => SpecialistLiteralMask.Create(text, protocol: SpecialistLiteralProtocol.CompactV4));
    }

    [Fact]
    public void Excessive_nesting_rejects_before_any_unbounded_parse()
    {
        var text = new string('‘', 65) + "word" + new string('’', 65);
        Should.Throw<InvalidDataException>(() => SpecialistLiteralMask.Create(text, protocol: SpecialistLiteralProtocol.CompactV4));
    }

    private static string Hash(string text) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text))).ToLowerInvariant();
}
