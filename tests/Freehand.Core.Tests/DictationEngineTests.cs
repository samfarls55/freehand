using Freehand.Abstractions;
using Freehand.Core;
using Freehand.Dictionary;
using Freehand.Testing;
using NetArchTest.Rules;
using Shouldly;
using Xunit;

namespace Freehand.CoreTests;

/// <summary>
/// Exercises the entire dictation path with fakes.
/// </summary>
/// <remarks>
/// This is the substitute for a Windows machine. Everything here runs on any platform, so a
/// regression in the state machine, the chunking, or the correction pass is caught on the
/// developer's own machine rather than discovered by a user on Windows.
/// </remarks>
public sealed class DictationEngineTests
{
    [Fact]
    public async Task Spoken_currency_is_formatted_before_delivery()
    {
        var hotkey = new FakeHotkeySource();
        var injector = new RecordingTextInjector();
        await using var engine = Build(FakeAudioCapture.Tone(0.4), hotkey,
            new FakeTranscriber("It costs twenty five dollars."), injector);
        await DictateAsync(hotkey, engine);
        engine.LastResult!.Text.ShouldBe("It costs $25.");
        injector.Injected.ShouldHaveSingleItem().ShouldBe("It costs $25. ");
    }

    private static DictationEngine Build(
        IAudioCapture capture,
        FakeHotkeySource hotkey,
        FakeTranscriber transcriber,
        RecordingTextInjector injector,
        params DictionaryEntry[] dictionary) =>
        new(capture, hotkey, transcriber, injector, () => dictionary, new FakeClock());

    /// <summary>Waits for actual audio before release, then waits for completion.</summary>
    private static async Task DictateAsync(FakeHotkeySource hotkey, DictationEngine engine)
    {
        var captured = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        void OnChanged(object? sender, EventArgs args)
        {
            if (engine.Level > 0) captured.TrySetResult();
        }
        engine.Changed += OnChanged;
        try
        {
            hotkey.Press();
            await captured.Task.WaitAsync(TimeSpan.FromSeconds(5));
            hotkey.Release();
            await LifecycleTests.WaitUntilAsync(() => engine.State == DictationState.Idle);
        }
        finally { engine.Changed -= OnChanged; }
    }

    [Fact]
    public async Task Speech_is_transcribed_corrected_and_injected()
    {
        var hotkey = new FakeHotkeySource();
        var transcriber = new FakeTranscriber("I use cloud code every day");
        var injector = new RecordingTextInjector();

        await using var engine = Build(
            FakeAudioCapture.Tone(1.0), hotkey, transcriber, injector,
            DictionaryEntry.Correction("cloud code", "Claude Code"));

        DictationResult? completed = null;
        engine.Completed += (_, r) => completed = r;

        await DictateAsync(hotkey, engine);

        injector.Injected.ShouldHaveSingleItem();
        injector.Injected[0].ShouldBe("I use Claude Code every day ");

        completed.ShouldNotBeNull();
        completed.Corrections.ShouldHaveSingleItem();
        completed.Corrections[0].To.ShouldBe("Claude Code");
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Consecutive_dictations_are_separated_by_a_space_without_changing_transcript_text(bool targeted)
    {
        var hotkey = new FakeHotkeySource();
        var injector = new RecordingTextInjector();
        ITextInjector destination = targeted ? new TargetedRecordingInjector(injector) : injector;
        await using var engine = new DictationEngine(FakeAudioCapture.Tone(0.4), hotkey,
            new FakeTranscriber("First sentence.", "Second sentence."), destination, () => []);

        await DictateAsync(hotkey, engine);
        engine.LastResult!.Text.ShouldBe("First sentence.");
        await DictateAsync(hotkey, engine);
        engine.LastResult!.Text.ShouldBe("Second sentence.");

        injector.Injected.Count.ShouldBe(2);
        string.Concat(injector.Injected).ShouldBe("First sentence. Second sentence. ");
    }

    [Theory]
    [InlineData("End. ")]
    [InlineData("End.  ")]
    [InlineData("End.\n")]
    [InlineData("End.\r\n")]
    [InlineData("End.\t")]
    [InlineData("")]
    public async Task Literal_correction_endings_are_preserved_without_an_extra_space(string replacement)
    {
        var hotkey = new FakeHotkeySource();
        var injector = new RecordingTextInjector();
        await using var engine = Build(FakeAudioCapture.Tone(0.4), hotkey,
            new FakeTranscriber("finish"), injector, DictionaryEntry.Correction("finish", replacement));

        await DictateAsync(hotkey, engine);

        injector.Injected.ShouldHaveSingleItem().ShouldBe(replacement);
        engine.LastResult!.Text.ShouldBe(replacement);
    }

    private sealed class TargetedRecordingInjector(RecordingTextInjector inner) : ITargetedTextInjector
    {
        public ValueTask<bool> InjectAsync(string text, CancellationToken cancellationToken) =>
            throw new InvalidOperationException("The captured target must be used.");

        public async ValueTask<DeliveryOutcome> InjectAsync(string text, ForegroundTarget target, CancellationToken cancellationToken) =>
            await inner.InjectAsync(text, cancellationToken) ? DeliveryOutcome.Delivered : DeliveryOutcome.PartialOrUncertain;
    }

    [Fact]
    public async Task Silence_injects_nothing()
    {
        var hotkey = new FakeHotkeySource();
        var injector = new RecordingTextInjector();

        // An engine that heard nothing returns empty — and empty must never be typed.
        await using var engine = Build(
            FakeAudioCapture.Silence(0.5), hotkey, new FakeTranscriber(""), injector);

        hotkey.Press();
        for (var i = 0; i < 2000 && engine.State != DictationState.Recording; i++) await Task.Yield();
        hotkey.Release();
        for (var i = 0; i < 20000 && engine.State != DictationState.Idle; i++) await Task.Yield();

        injector.Injected.ShouldBeEmpty();
    }

    [Fact]
    public async Task Release_without_press_is_ignored()
    {
        var hotkey = new FakeHotkeySource();
        var injector = new RecordingTextInjector();
        await using var engine = Build(
            FakeAudioCapture.Tone(0.2), hotkey, new FakeTranscriber("hello"), injector);

        hotkey.Release();
        for (var i = 0; i < 500; i++) await Task.Yield();

        engine.State.ShouldBe(DictationState.Idle);
        injector.Injected.ShouldBeEmpty();
    }

    [Fact]
    public async Task Dictionary_terms_are_offered_to_the_engine_as_bias()
    {
        var hotkey = new FakeHotkeySource();
        var transcriber = new FakeTranscriber("anything");

        await using var engine = Build(
            FakeAudioCapture.Tone(0.4), hotkey, transcriber, new RecordingTextInjector(),
            DictionaryEntry.Term("Anthropic"),
            DictionaryEntry.Correction("cloud code", "Claude Code"));

        await DictateAsync(hotkey, engine);

        // Both the plain term and the *write* side of the correction get biased — the whole
        // point is to nudge the recogniser toward the correct spelling.
        transcriber.LastBias.ShouldContain("Anthropic");
        transcriber.LastBias.ShouldContain("Claude Code");
    }

    [Fact]
    public async Task State_returns_to_idle_after_a_dictation()
    {
        var hotkey = new FakeHotkeySource();
        await using var engine = Build(
            FakeAudioCapture.Tone(0.3), hotkey, new FakeTranscriber("done"), new RecordingTextInjector());

        engine.State.ShouldBe(DictationState.Idle);
        await DictateAsync(hotkey, engine);
        engine.State.ShouldBe(DictationState.Idle);
        engine.Level.ShouldBe(0);
    }

    /// <summary>
    /// The boundary is enforced by the compiler via CA1416, but this fails louder and names
    /// the reason: anything reachable from Core must run in CI on any platform.
    /// </summary>
    [Fact]
    public void Core_does_not_depend_on_any_platform_project()
    {
        var result = Types.InAssembly(typeof(DictationEngine).Assembly)
            .That().ResideInNamespace("Freehand.Core")
            .ShouldNot().HaveDependencyOn("Freehand.Platform")
            .GetResult();

        result.IsSuccessful.ShouldBeTrue(
            "Freehand.Core must stay platform-neutral: " +
            string.Join(", ", result.FailingTypeNames ?? []));
    }
}

/// <summary>Chunking behaviour around the encoder's hard limit.</summary>
public sealed class AudioSegmenterTests
{
    private static ReadOnlyMemory<float> Seconds(int n) =>
        new float[n * AudioChunk.SampleRate];

    [Fact]
    public void Short_audio_is_one_segment_and_is_not_copied()
    {
        var audio = Seconds(5);
        var pieces = AudioSegmenter.Split(audio);

        pieces.ShouldHaveSingleItem();
        pieces[0].Length.ShouldBe(audio.Length);
    }

    [Fact]
    public void Audio_at_the_limit_is_still_one_segment()
    {
        AudioSegmenter.Split(Seconds(AudioSegmenter.MaxSegmentSeconds)).ShouldHaveSingleItem();
    }

    [Fact]
    public void Long_audio_is_split_and_every_piece_is_under_the_limit()
    {
        var pieces = AudioSegmenter.Split(Seconds(200));

        pieces.Count.ShouldBeGreaterThan(1);
        foreach (var piece in pieces)
        {
            piece.Length.ShouldBeLessThanOrEqualTo(
                AudioSegmenter.MaxSegmentSeconds * AudioChunk.SampleRate);
            piece.Length.ShouldBeGreaterThan(0);
        }
    }

    [Fact]
    public void Splitting_loses_no_samples()
    {
        var pieces = AudioSegmenter.Split(Seconds(200));
        pieces.Sum(p => p.Length).ShouldBe(200 * AudioChunk.SampleRate);
    }

    /// <summary>
    /// 410 seconds is past the point where the encoder's position table overflows and
    /// inference throws rather than degrading. Nothing may reach it.
    /// </summary>
    [Fact]
    public void Nothing_ever_reaches_the_encoder_ceiling()
    {
        var pieces = AudioSegmenter.Split(Seconds(AudioSegmenter.EncoderCeilingSeconds + 100));

        foreach (var piece in pieces)
        {
            var seconds = (double)piece.Length / AudioChunk.SampleRate;
            seconds.ShouldBeLessThan(AudioSegmenter.EncoderCeilingSeconds);
        }
    }

    [Fact]
    public void A_cut_lands_in_the_quiet_part_rather_than_mid_word()
    {
        // Loud throughout, with one silent second placed inside the search window that
        // precedes the ideal cut point. The cut should be drawn to it.
        var total = AudioSegmenter.MaxSegmentSeconds * 2 * AudioChunk.SampleRate;
        var samples = new float[total];
        Array.Fill(samples, 0.5f);

        var quietStart = (AudioSegmenter.MaxSegmentSeconds - 3) * AudioChunk.SampleRate;
        Array.Clear(samples, quietStart, AudioChunk.SampleRate);

        var pieces = AudioSegmenter.Split(samples);
        var firstCut = pieces[0].Length;

        firstCut.ShouldBeGreaterThanOrEqualTo(quietStart);
        firstCut.ShouldBeLessThanOrEqualTo(quietStart + AudioChunk.SampleRate);
    }

    [Fact]
    public void A_pause_is_preferred_to_a_brief_quiet_sound_inside_a_word()
    {
        var samples = Enumerable.Repeat(0.5f, 30 * AudioChunk.SampleRate).ToArray();
        var pause = 13 * AudioChunk.SampleRate;
        Array.Fill(samples, 0.01f, pause, AudioChunk.SampleRate / 5);
        Array.Clear(samples, 14 * AudioChunk.SampleRate, AudioChunk.SampleRate / 25);
        var cut = AudioSegmenter.Split(samples)[0].Length;
        cut.ShouldBeInRange(pause, pause + AudioChunk.SampleRate / 5);
    }
}
