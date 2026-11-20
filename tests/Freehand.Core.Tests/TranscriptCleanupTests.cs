using Freehand.Abstractions;
using Freehand.Core;
using Freehand.Dictionary;
using Freehand.Testing;
using Shouldly;
using Xunit;

namespace Freehand.CoreTests;

public sealed class TranscriptCleanupTests
{
    [Fact]
    public async Task Cleanup_receives_complete_formatted_text_and_backtracks_before_one_delivery()
    {
        var key = new FakeHotkeySource(); var injector = new RecordingTextInjector();
        var speech = new FakeTranscriber("Um send it Friday, sorry Monday for twenty five dollars.");
        var processor = new Processor((_, _) => ValueTask.FromResult("Send it Monday for $25."));
        await using var engine = Build(key, speech, injector, processor);
        var cleaning = false; engine.Changed += (_, _) => cleaning |= engine.State == DictationState.Cleaning;

        await DictateAsync(key, engine);

        processor.LastInput.ShouldBe("Um send it Friday, sorry Monday for $25.");
        engine.LastResult!.OriginalText.ShouldBe(processor.LastInput);
        engine.LastResult.Text.ShouldBe("Send it Monday for $25.");
        engine.LastResult.CleanupOutcome.ShouldBe(TranscriptCleanupOutcome.Applied);
        engine.LastResult.CleanupTime.ShouldBeGreaterThan(TimeSpan.Zero);
        cleaning.ShouldBeTrue(); speech.SegmentLengths.ShouldHaveSingleItem();
        injector.Injected.ShouldHaveSingleItem().ShouldBe("Send it Monday for $25. ");
    }

    [Fact]
    public async Task Number_formatting_realigns_dictionary_literals_and_keeps_their_whitespace()
    {
        const string literal = "Claude Code  \r\n";
        var key = new FakeHotkeySource(); var injector = new RecordingTextInjector();
        var processor = new Processor((text, _) => ValueTask.FromResult(text));
        await using var engine = Build(key, new FakeTranscriber("for twenty five dollars use cloud code"), injector, processor,
            [DictionaryEntry.Correction("cloud code", literal)]);

        await DictateAsync(key, engine);

        processor.LastInput.ShouldStartWith("for $25 use [[FREEHAND_LITERAL_");
        processor.LastInput.ShouldContain("_START]]" + literal + "[[FREEHAND_LITERAL_");
        engine.LastResult!.Text.ShouldBe("for $25 use " + literal);
        engine.LastResult.CleanupOutcome.ShouldBe(TranscriptCleanupOutcome.Unchanged);
        injector.Injected.ShouldHaveSingleItem().ShouldBe(engine.LastResult.Text);
    }

    [Theory]
    [InlineData("change")]
    [InlineData("remove")]
    [InlineData("duplicate")]
    public async Task Broken_dictionary_protection_falls_back_without_running_corrections_twice(string damage)
    {
        var key = new FakeHotkeySource(); var injector = new RecordingTextInjector();
        var processor = new Processor((text, _) => ValueTask.FromResult(damage switch
        {
            "change" => text.Replace("Claude Code", "ClaudeCode", StringComparison.Ordinal),
            "remove" => text.Replace("[[FREEHAND_LITERAL_", "[[REMOVED_", StringComparison.Ordinal),
            _ => text + text,
        }));
        await using var engine = Build(key, new FakeTranscriber("cloud code"), injector, processor,
            [DictionaryEntry.Correction("cloud code", "Claude Code"), DictionaryEntry.Correction("Claude Code", "Other")]);

        await DictateAsync(key, engine);

        // Both dictionary rules run once in their existing stable order. Cleanup must
        // not repeat the correction pass as a way to repair damaged model output.
        engine.LastResult!.CleanupOutcome.ShouldBe(TranscriptCleanupOutcome.Rejected);
        engine.LastResult.Text.ShouldBe("Claude Code");
        injector.Injected.ShouldHaveSingleItem().ShouldBe("Claude Code ");
    }

    [Theory]
    [InlineData("")]
    [InlineData("<think>Some reasoning</think>Hello.")]
    [InlineData("Here is the cleaned transcript:\nHello.")]
    [InlineData("```\nHello.\n```")]
    [InlineData("Hello.\0")]
    public async Task Empty_or_framed_output_keeps_the_original(string output)
    {
        var key = new FakeHotkeySource(); var injector = new RecordingTextInjector();
        var processor = new Processor((_, _) => ValueTask.FromResult(output));
        await using var engine = Build(key, new FakeTranscriber("Hello."), injector, processor);

        await DictateAsync(key, engine);

        engine.LastResult!.Text.ShouldBe("Hello.");
        engine.LastResult.CleanupOutcome.ShouldBe(TranscriptCleanupOutcome.Rejected);
        injector.Injected.ShouldHaveSingleItem().ShouldBe("Hello. ");
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Processor_failure_does_not_retry_speech_or_lose_usable_text(bool cancelled)
    {
        var key = new FakeHotkeySource(); var injector = new RecordingTextInjector(); var speech = new FakeTranscriber("Hello.");
        var processor = new Processor((_, _) =>
        {
            if (cancelled) throw new OperationCanceledException();
            throw new InvalidOperationException();
        });
        await using var engine = Build(key, speech, injector, processor);

        await DictateAsync(key, engine);

        engine.LastResult!.CleanupOutcome.ShouldBe(TranscriptCleanupOutcome.Failed);
        engine.LastResult.Text.ShouldBe("Hello.");
        speech.SegmentLengths.ShouldHaveSingleItem(); injector.Injected.ShouldHaveSingleItem();
    }

    [Fact]
    public async Task Timeout_delivers_original_once_and_never_overlaps_or_delivers_a_late_response()
    {
        var key = new FakeHotkeySource(); var injector = new RecordingTextInjector();
        var late = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        var processor = new Processor((_, _) => new ValueTask<string>(late.Task));
        await using var engine = new DictationEngine(FakeAudioCapture.Tone(0.2), key, new FakeTranscriber("Hello."), injector,
            () => [], transcriptPostProcessor: processor, cleanupTimeout: TimeSpan.FromMilliseconds(50));
        try
        {
            await DictateAsync(key, engine);
            engine.LastResult!.CleanupOutcome.ShouldBe(TranscriptCleanupOutcome.TimedOut);
            processor.Token.IsCancellationRequested.ShouldBeTrue();
            await DictateAsync(key, engine);
            engine.LastResult!.CleanupOutcome.ShouldBe(TranscriptCleanupOutcome.Failed);
            processor.Calls.ShouldBe(1);
        }
        finally { late.TrySetResult("Late rewrite."); }
        await Task.Delay(20);
        injector.Injected.ShouldBe(["Hello. ", "Hello. "]);
        engine.LastResult!.Text.ShouldBe("Hello.");
    }

    [Fact]
    public async Task Focus_is_rechecked_after_cleanup_and_the_final_text_remains_copyable()
    {
        var key = new FakeHotkeySource(); var injector = new RecordingTextInjector(); var focus = new Foreground();
        var finish = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        var processor = new Processor((_, token) => new ValueTask<string>(finish.Task.WaitAsync(token)));
        await using var engine = new DictationEngine(FakeAudioCapture.Tone(0.2), key, new FakeTranscriber("Hello."), injector,
            () => [], foreground: focus, transcriptPostProcessor: processor);
        await ReleaseAsync(key, engine);
        await processor.Started.Task.WaitAsync(TimeSpan.FromSeconds(5));
        focus.Current = new(2, 20); finish.TrySetResult("Hello there.");
        await LifecycleTests.WaitUntilAsync(() => engine.State == DictationState.Idle);

        injector.Injected.ShouldBeEmpty();
        engine.LastResult!.Text.ShouldBe("Hello there.");
        engine.LastResult.Delivery.ShouldBe(DeliveryOutcome.TargetChanged);
    }

    [Fact]
    public async Task Cleanup_preference_is_snapshotted_at_recording_acceptance()
    {
        var key = new FakeHotkeySource(); var injector = new RecordingTextInjector(); var enabled = true;
        var processor = new Processor((text, _) => ValueTask.FromResult(text));
        await using var engine = new DictationEngine(FakeAudioCapture.Tone(0.2), key, new FakeTranscriber("Hello."), injector,
            () => [], transcriptPostProcessor: processor, cleanupEnabled: () => enabled);
        var captured = CaptureSignal(engine);
        key.Press(); await captured.WaitAsync(TimeSpan.FromSeconds(5)); enabled = false; key.Release();
        await LifecycleTests.WaitUntilAsync(() => engine.State == DictationState.Idle);
        engine.LastResult!.CleanupOutcome.ShouldBe(TranscriptCleanupOutcome.Unchanged);
        await DictateAsync(key, engine);
        engine.LastResult!.CleanupOutcome.ShouldBe(TranscriptCleanupOutcome.Disabled);
        engine.LastResult.OriginalText.ShouldBeNull(); processor.Calls.ShouldBe(1);
    }

    [Fact]
    public async Task Quit_cancels_cleanup_disposes_the_owned_processor_and_prevents_delivery()
    {
        var key = new FakeHotkeySource(); var injector = new RecordingTextInjector();
        var processor = new Processor(async (_, token) => { await Task.Delay(Timeout.InfiniteTimeSpan, token); return "unreachable"; });
        var engine = Build(key, new FakeTranscriber("Hello."), injector, processor);
        await ReleaseAsync(key, engine);
        await processor.Started.Task.WaitAsync(TimeSpan.FromSeconds(5));

        await engine.DisposeAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(5));

        processor.Token.IsCancellationRequested.ShouldBeTrue(); processor.Disposed.ShouldBeTrue();
        engine.State.ShouldBe(DictationState.Stopping); injector.Injected.ShouldBeEmpty(); engine.LastResult.ShouldBeNull();
    }

    [Fact]
    public void History_remains_compatible_with_old_records_and_retains_optional_cleanup_fields()
    {
        var directory = Path.Combine(Path.GetTempPath(), "freehand-cleanup-" + Guid.NewGuid());
        Directory.CreateDirectory(directory);
        try
        {
            var path = Path.Combine(directory, "history.jsonl");
            File.WriteAllText(path, "{\"Text\":\"Old transcript\"}\n");
            var store = new TranscriptStore(path);
            store.Records.ShouldHaveSingleItem().OriginalText.ShouldBeNull();
            store.Add(new TranscriptRecord { Text = "Monday.", OriginalText = "Friday, sorry Monday.", CleanupOutcome = TranscriptCleanupOutcome.Applied, CleanupSeconds = 0.5 });
            var record = new TranscriptStore(path).Records[0];
            record.Text.ShouldBe("Monday."); record.OriginalText.ShouldBe("Friday, sorry Monday.");
            record.CleanupOutcome.ShouldBe(TranscriptCleanupOutcome.Applied); record.CleanupSeconds.ShouldBe(0.5);
        }
        finally { Directory.Delete(directory, true); }
    }

    private static DictationEngine Build(FakeHotkeySource key, FakeTranscriber speech, RecordingTextInjector injector,
        Processor processor, IReadOnlyList<DictionaryEntry>? entries = null) =>
        new(FakeAudioCapture.Tone(0.2), key, speech, injector, () => entries ?? [], transcriptPostProcessor: processor);

    private static Task CaptureSignal(DictationEngine engine)
    {
        var captured = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        void Changed(object? sender, EventArgs args)
        {
            if (engine.Level <= 0) return;
            engine.Changed -= Changed; captured.TrySetResult();
        }
        engine.Changed += Changed;
        return captured.Task;
    }
    private static async Task ReleaseAsync(FakeHotkeySource key, DictationEngine engine)
    {
        var captured = CaptureSignal(engine); key.Press();
        await captured.WaitAsync(TimeSpan.FromSeconds(5)); key.Release();
    }
    private static async Task DictateAsync(FakeHotkeySource key, DictationEngine engine)
    {
        await ReleaseAsync(key, engine);
        await LifecycleTests.WaitUntilAsync(() => engine.State == DictationState.Idle);
    }
    private sealed class Processor(Func<string, CancellationToken, ValueTask<string>> process) : ITranscriptPostProcessor
    {
        public string LastInput { get; private set; } = string.Empty;
        public int Calls { get; private set; }
        public CancellationToken Token { get; private set; }
        public bool Disposed { get; private set; }
        public TaskCompletionSource Started { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public ValueTask<string> ProcessAsync(string text, CancellationToken cancellationToken)
        {
            Calls++; LastInput = text; Token = cancellationToken; Started.TrySetResult();
            return process(text, cancellationToken);
        }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
    private sealed class Foreground : IForegroundWindow
    {
        public ForegroundTarget Current { get; set; } = new(1, 10);
        public ForegroundTarget Capture() => Current;
        public bool IsCurrent(ForegroundTarget target) => target == Current;
    }
}
