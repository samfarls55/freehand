using Freehand.Speech;
using Shouldly;
using Xunit;

namespace Freehand.CoreTests;

public sealed class ParakeetHotwordTests
{
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
