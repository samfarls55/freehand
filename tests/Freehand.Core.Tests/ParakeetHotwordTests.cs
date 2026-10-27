using Freehand.Speech;
using Freehand.Dictionary;
using Shouldly;
using Xunit;

namespace Freehand.CoreTests;

public sealed class ParakeetHotwordTests
{
    [Fact]
    public void Unsupported_entries_do_not_consume_the_recognition_hint_limit()
    {
        var entries = Enumerable.Range(0, 40).Select(i => DictionaryEntry.Term($"https://example.com/{i}"))
            .Append(DictionaryEntry.Term("Claude Code"));
        var hotwords = new ParakeetHotwords(Path.Combine(AppContext.BaseDirectory, ParakeetHotwords.VocabularyFile));
        // Exercise selection before the worker request is bounded.
        DictionaryCorrector.BiasPhrases(entries, hotwords.Supports).ShouldBe(["Claude Code"]);
    }

    [Fact]
    public void Hotwords_preserve_phrase_boundaries_and_reject_native_control_syntax()
    {
        var hotwords = new ParakeetHotwords(Path.Combine(AppContext.BaseDirectory, ParakeetHotwords.VocabularyFile));
        hotwords.Format(["Claude Code", "Claude Code", "Freehand", "phrase:999", "one/two", "line\nbreak", "snow☃", new string('x', 257)])
            .ShouldBe("Claude Code/claude code/Freehand/freehand");
        hotwords.Format([]).ShouldBeEmpty();
        hotwords.Format(["Anthropic"]).ShouldBe("Anthropic/anthropic");
    }

    [Fact]
    public void Damaged_tokenizer_fails_before_native_loading()
    {
        var path = Path.GetTempFileName();
        try
        {
            File.WriteAllText(path, "corrupt");
            Should.Throw<InvalidDataException>(() => new ParakeetHotwords(path));
        }
        finally { File.Delete(path); }
    }
}
