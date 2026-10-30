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
        injector.Injected.ShouldHaveSingleItem().ShouldBe("Claude Code ");
        engine.LastResult!.AudioDuration.TotalSeconds.ShouldBe(15.04, 0.0001);
    }

    [Fact]
    public async Task Eight_second_policy_decodes_before_ten_second_release_and_preserves_every_sample()
    {
        var capture = new QueuedCapture();
        var speech = new ObservedSpeech();
        var key = new FakeHotkeySource();
        var injector = new RecordingTextInjector();
        var completed = 0;
        var audio = Enumerable.Range(0, 10 * AudioChunk.SampleRate)
            .Select(sample => 0.25f + (float)sample / (20 * AudioChunk.SampleRate)).ToArray();
        Array.Fill(audio, 0f, 6 * AudioChunk.SampleRate + AudioChunk.SampleRate / 5, 2 * AudioChunk.SampleRate / 5);
        await using var engine = new DictationEngine(capture, key, speech, injector, () => [],
            options: new DictationOptions { MaxSegmentSeconds = 8 });
        engine.Completed += (_, _) => completed++;
        key.Press();
        var firstChunkSamples = 8 * AudioChunk.SampleRate + 320;
        await capture.SendAndWaitAsync(audio[..firstChunkSamples]).WaitAsync(TimeSpan.FromSeconds(2));
        await speech.FirstSegment.Task.WaitAsync(TimeSpan.FromSeconds(2));
        engine.State.ShouldBe(DictationState.Recording);
        completed.ShouldBe(0);
        injector.Injected.ShouldBeEmpty();
        speech.Samples.ShouldHaveSingleItem().ShouldBeLessThanOrEqualTo(8 * AudioChunk.SampleRate);
        await capture.SendAndWaitAsync(audio[firstChunkSamples..]).WaitAsync(TimeSpan.FromSeconds(2));
        injector.Injected.ShouldBeEmpty();
        key.Release();
        await LifecycleTests.WaitUntilAsync(() => engine.State == DictationState.Idle);
        speech.Samples.Count.ShouldBe(2);
        speech.Audio.SelectMany(segment => segment.ToArray()).ShouldBe(audio.Concat(Tone(320)));
        speech.Samples.ShouldAllBe(count => count <= 8 * AudioChunk.SampleRate);
        engine.LastResult!.AudioDuration.TotalSeconds.ShouldBe(10.02, 0.0001);
        completed.ShouldBe(1);
        injector.Injected.ShouldHaveSingleItem();
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
        injector.Injected.ShouldHaveSingleItem().ShouldBe("recovered recovered recovered ");
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
        private readonly Channel<(float[] Samples, TaskCompletionSource? Consumed)> _chunks =
            Channel.CreateUnbounded<(float[], TaskCompletionSource?)>();
        public bool IsCapturing { get; private set; }
        internal void Send(float[] samples) => _chunks.Writer.TryWrite((samples, null));
        internal Task SendAndWaitAsync(float[] samples)
        {
            var consumed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            _chunks.Writer.TryWrite((samples, consumed));
            return consumed.Task;
        }
        internal void Fail() => _chunks.Writer.TryComplete(new IOException("Microphone disconnected"));
        public async IAsyncEnumerable<AudioChunk> CaptureAsync([EnumeratorCancellation] CancellationToken cancellationToken)
        {
            IsCapturing = true;
            while (true)
            {
                (float[] Samples, TaskCompletionSource? Consumed) chunk;
                try { chunk = await _chunks.Reader.ReadAsync(cancellationToken); }
                catch (OperationCanceledException) { break; }
                yield return new AudioChunk(chunk.Samples);
                chunk.Consumed?.TrySetResult();
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
        internal List<ReadOnlyMemory<float>> Audio { get; } = [];
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
            Audio.Add(samples);
            FirstSegment.TrySetResult();
            if (HoldInference) await Task.Delay(Timeout.Infinite, cancellationToken);
            if (FailSecondSegment && Samples.Count == 2) { Failed.TrySetResult(); throw new IOException("Worker failed"); }
            return FailSecondSegment ? Resets == 0 ? "stale" : "recovered" : Samples.Count == 1 ? "cloud" : "code";
        }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
