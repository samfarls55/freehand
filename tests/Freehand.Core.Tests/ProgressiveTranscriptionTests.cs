using System.Runtime.CompilerServices;
using System.Threading.Channels;
using Freehand.Abstractions;
using Freehand.Core;
using Freehand.Dictionary;
using Freehand.Testing;
using Shouldly;
using Xunit;

namespace Freehand.CoreTests;

public sealed class ProgressiveTranscriptionTests
{
    [Fact]
    public async Task Completed_segments_are_decoded_before_release_and_delivery_waits_for_the_tail()
    {
        var capture = new QueuedCapture();
        var speech = new ObservedSpeech();
        var key = new FakeHotkeySource();
        var injector = new RecordingTextInjector();
        await using var engine = new DictationEngine(capture, key, speech, injector,
            () => [DictionaryEntry.Correction("cloud code", "Claude Code")]);
        key.Press();
        capture.Send(Tone(15 * AudioChunk.SampleRate + 320));
        await speech.FirstSegment.Task.WaitAsync(TimeSpan.FromSeconds(2));
        engine.State.ShouldBe(DictationState.Recording);
        injector.Injected.ShouldBeEmpty();
        key.Release();
        await LifecycleTests.WaitUntilAsync(() => engine.State == DictationState.Idle);
        speech.Samples.Sum().ShouldBe(15 * AudioChunk.SampleRate + 640);
        speech.Samples.ShouldAllBe(n => n <= 15 * AudioChunk.SampleRate);
        injector.Injected.ShouldHaveSingleItem().ShouldBe("Claude Code");
        engine.LastResult!.AudioDuration.TotalSeconds.ShouldBe(15.04, 0.0001);
    }

    [Fact]
    public async Task Failed_progressive_inference_replays_the_recording_once_and_discards_partial_text()
    {
        var capture = new QueuedCapture();
        var speech = new ObservedSpeech { FailSecondSegment = true };
        var key = new FakeHotkeySource();
        var injector = new RecordingTextInjector();
        await using var engine = new DictationEngine(capture, key, speech, injector, () => []);
        key.Press();
        capture.Send(Tone(31 * AudioChunk.SampleRate));
        await speech.Failed.Task.WaitAsync(TimeSpan.FromSeconds(2));
        injector.Injected.ShouldBeEmpty();
        key.Release();
        await LifecycleTests.WaitUntilAsync(() => engine.State == DictationState.Idle);
        speech.Resets.ShouldBe(1);
        speech.Samples.Skip(2).Sum().ShouldBe(31 * AudioChunk.SampleRate + 320);
        injector.Injected.ShouldHaveSingleItem().ShouldBe("recovered recovered recovered");
    }

    [Fact]
    public async Task Quit_cancels_an_inference_started_during_recording()
    {
        var capture = new QueuedCapture();
        var speech = new ObservedSpeech { HoldInference = true };
        var key = new FakeHotkeySource();
        var injector = new RecordingTextInjector();
        var engine = new DictationEngine(capture, key, speech, injector, () => []);
        key.Press();
        capture.Send(Tone(16 * AudioChunk.SampleRate));
        await speech.FirstSegment.Task.WaitAsync(TimeSpan.FromSeconds(2));
        await engine.DisposeAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(2));
        injector.Injected.ShouldBeEmpty();
        speech.Disposed.ShouldBeTrue();
    }

    [Fact]
    public async Task Microphone_failure_cancels_background_inference_and_returns_to_idle()
    {
        var capture = new QueuedCapture();
        var speech = new ObservedSpeech { HoldInference = true };
        var key = new FakeHotkeySource();
        var injector = new RecordingTextInjector();
        await using var engine = new DictationEngine(capture, key, speech, injector, () => []);
        key.Press();
        capture.Send(Tone(16 * AudioChunk.SampleRate));
        await speech.FirstSegment.Task.WaitAsync(TimeSpan.FromSeconds(2));
        capture.Fail();
        await LifecycleTests.WaitUntilAsync(() => engine.State == DictationState.Idle);
        injector.Injected.ShouldBeEmpty();
        engine.Feedback!.Outcome.ShouldBe(DictationOutcome.CaptureFailure);
    }

    [Fact]
    public async Task Progressive_capture_obeys_the_recording_limit_including_the_final_callback()
    {
        var capture = new QueuedCapture();
        var speech = new ObservedSpeech();
        var key = new FakeHotkeySource();
        var injector = new RecordingTextInjector();
        await using var engine = new DictationEngine(capture, key, speech, injector, () => [],
            options: new DictationOptions { RecordingLimit = TimeSpan.FromSeconds(16) });
        key.Press();
        capture.Send(Tone(17 * AudioChunk.SampleRate));
        await LifecycleTests.WaitUntilAsync(() => engine.State == DictationState.Idle);
        speech.Samples.Sum().ShouldBe(16 * AudioChunk.SampleRate);
        injector.Injected.ShouldHaveSingleItem();
        engine.LastResult!.AudioDuration.ShouldBe(TimeSpan.FromSeconds(16));
    }

    private static float[] Tone(int samples) => Enumerable.Repeat(0.5f, samples).ToArray();

    private sealed class QueuedCapture : IAudioCapture
    {
        private readonly Channel<float[]> _chunks = Channel.CreateUnbounded<float[]>();
        public bool IsCapturing { get; private set; }
        internal void Send(float[] samples) => _chunks.Writer.TryWrite(samples);
        internal void Fail() => _chunks.Writer.TryComplete(new IOException("Microphone disconnected"));
        public async IAsyncEnumerable<AudioChunk> CaptureAsync([EnumeratorCancellation] CancellationToken cancellationToken)
        {
            IsCapturing = true;
            while (true)
            {
                float[] samples;
                try { samples = await _chunks.Reader.ReadAsync(cancellationToken); }
                catch (OperationCanceledException) { break; }
                yield return new AudioChunk(samples);
            }
            // Preserve the capture callback that arrives while the device stops.
            yield return new AudioChunk(Tone(320));
            IsCapturing = false;
        }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }

    private sealed class ObservedSpeech : ISpeechSession
    {
        internal bool FailSecondSegment { get; init; }
        internal bool HoldInference { get; init; }
        internal List<int> Samples { get; } = [];
        internal TaskCompletionSource FirstSegment { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal TaskCompletionSource Failed { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal int Resets { get; private set; }
        internal bool Disposed { get; private set; }
        public bool IsReady => true;
        public ModelState State => ModelState.Ready;
        public event EventHandler? Changed { add { } remove { } }
        public ValueTask BeginWorkAsync(CancellationToken cancellationToken) => ValueTask.CompletedTask;
        public void FinishWork() { }
        public void SetIdleTimeout(TimeSpan timeout) { }
        public ValueTask<bool> LoadAsync(CancellationToken cancellationToken) => ValueTask.FromResult(true);
        public ValueTask ResetAsync(CancellationToken cancellationToken) { Resets++; return ValueTask.CompletedTask; }
        public async ValueTask<string> TranscribeAsync(ReadOnlyMemory<float> samples, IReadOnlyList<string> biasPhrases, CancellationToken cancellationToken)
        {
            Samples.Add(samples.Length);
            FirstSegment.TrySetResult();
            if (HoldInference) await Task.Delay(Timeout.Infinite, cancellationToken);
            if (FailSecondSegment && Samples.Count == 2) { Failed.TrySetResult(); throw new IOException("Worker failed"); }
            return FailSecondSegment ? Resets == 0 ? "stale" : "recovered" : Samples.Count == 1 ? "cloud" : "code";
        }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
