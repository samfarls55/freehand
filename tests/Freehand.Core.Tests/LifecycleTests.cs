using System.Runtime.CompilerServices;
using Freehand.Abstractions;
using Freehand.Core;
using Freehand.Testing;
using Shouldly;
using Xunit;

namespace Freehand.CoreTests;

public sealed class LifecycleTests
{
    [Fact]
    public async Task Configuration_of_retained_audio_does_not_reschedule_dictation_state_handlers()
    {
        var capture = new DrainingCapture(); var key = new FakeHotkeySource();
        await using var engine = new DictationEngine(capture, key, new FailingSpeech(10), new RecordingTextInjector(), () => []);
        key.Press(); await capture.Started.Task; key.Release();
        await WaitUntilAsync(() => engine.State == DictationState.AwaitingRetry);
        var rescheduled = 0;
        engine.Changed += (_, _) => rescheduled++;
        await engine.ApplyConfigurationAsync(() => Task.CompletedTask);
        rescheduled.ShouldBe(0);
        engine.State.ShouldBe(DictationState.AwaitingRetry); engine.HasPendingAudio.ShouldBeTrue();
    }

    [Fact]
    public async Task Update_reservation_refuses_active_or_retained_audio_and_blocks_new_recordings_until_released()
    {
        var capture = new DrainingCapture(); var key = new FakeHotkeySource();
        await using var engine = new DictationEngine(capture, key, new FailingSpeech(10), new RecordingTextInjector(), () => []);
        key.Press(); await capture.Started.Task;
        engine.TryPrepareForUpdate().ShouldBeFalse();
        key.Release();
        await WaitUntilAsync(() => engine.State == DictationState.AwaitingRetry);
        engine.TryPrepareForUpdate().ShouldBeFalse(); engine.HasPendingAudio.ShouldBeTrue();
        engine.Discard();
        engine.TryPrepareForUpdate().ShouldBeTrue();
        key.Press(); engine.State.ShouldBe(DictationState.Idle);
        var applied = false;
        await engine.ApplyConfigurationAsync(() => { applied = true; return Task.CompletedTask; });
        applied.ShouldBeFalse();
        engine.ResumeAfterUpdateFailure();
        key.Press(); engine.State.ShouldBe(DictationState.Recording); key.Release();
    }

    [Fact]
    public async Task Update_reservation_waits_for_loading_and_pending_text_delivery()
    {
        var capture = new DrainingCapture(); var speech = new ControlledSpeech(); var key = new FakeHotkeySource();
        await using var engine = new DictationEngine(capture, key, speech, new RecordingTextInjector(), () => []);
        engine.Changed += (_, _) =>
        {
            if (engine.HasPendingAudio) engine.TryPrepareForUpdate().ShouldBeFalse();
        };
        key.Press(); await speech.LoadStarted.Task; key.Release();
        engine.TryPrepareForUpdate().ShouldBeFalse();
        speech.AllowLoad.TrySetResult();
        await WaitUntilAsync(() => engine.State == DictationState.Idle);
        engine.LastResult.ShouldNotBeNull(); engine.TryPrepareForUpdate().ShouldBeTrue();
    }

    [Fact]
    public async Task Model_repair_can_run_while_failed_audio_is_retained_and_retry_waits()
    {
        var capture = new DrainingCapture(); var speech = new FailingSpeech(2); var key = new FakeHotkeySource();
        var injector = new RecordingTextInjector();
        await using var engine = new DictationEngine(capture, key, speech, injector, () => []);
        key.Press(); await capture.Started.Task; key.Release();
        await WaitUntilAsync(() => engine.State == DictationState.AwaitingRetry);
        var applied = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var finish = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var configuration = engine.ApplyConfigurationAsync(async () => { applied.TrySetResult(); await finish.Task; });
        try
        {
            await applied.Task.WaitAsync(TimeSpan.FromSeconds(1));
            engine.Retry();
            engine.State.ShouldBe(DictationState.AwaitingRetry);
            engine.HasPendingAudio.ShouldBeTrue();
            speech.Calls.ShouldBe(2);
        }
        finally { finish.TrySetResult(); await configuration; }
        engine.Retry(); await WaitUntilAsync(() => engine.State == DictationState.Idle);
        injector.Injected.ShouldHaveSingleItem();
    }
    [Fact]
    public async Task Early_release_during_loading_returns_to_a_usable_state()
    {
        var capture = new DrainingCapture(); var speech = new ControlledSpeech(); var hotkey = new FakeHotkeySource();
        await using var engine = new DictationEngine(capture, hotkey, speech, new RecordingTextInjector(), () => []);
        hotkey.Press(); hotkey.Release(); speech.AllowLoad.TrySetResult();
        await WaitUntilAsync(() => engine.State == DictationState.Idle);
        engine.Level.ShouldBe(0);
        hotkey.Press(); await capture.Started.Task; hotkey.Release();
        await WaitUntilAsync(() => engine.State == DictationState.Idle);
    }

    [Fact]
    public async Task One_automatic_retry_then_manual_retry_keeps_the_job_and_delivers_once()
    {
        var capture = new DrainingCapture(); var speech = new FailingSpeech(2); var hotkey = new FakeHotkeySource();
        var injector = new RecordingTextInjector();
        await using var engine = new DictationEngine(capture, hotkey, speech, injector, () => []);
        var completed = 0; engine.Completed += (_, _) => completed++;
        hotkey.Press(); await capture.Started.Task; hotkey.Release();
        await WaitUntilAsync(() => engine.State == DictationState.AwaitingRetry);
        var job = engine.Feedback!.JobId;
        speech.Calls.ShouldBe(2); injector.Injected.ShouldBeEmpty(); engine.HasPendingAudio.ShouldBeTrue();
        hotkey.Press(); engine.Feedback!.Outcome.ShouldBe(DictationOutcome.Busy);
        engine.Retry();
        await WaitUntilAsync(() => engine.State == DictationState.Idle);
        engine.LastResult!.JobId.ShouldBe(job); speech.Calls.ShouldBe(3);
        completed.ShouldBe(1); injector.Injected.ShouldHaveSingleItem(); engine.HasPendingAudio.ShouldBeFalse();
    }

    [Fact]
    public async Task Discard_releases_the_only_failed_recording_and_allows_another_attempt()
    {
        var capture = new DrainingCapture(); var hotkey = new FakeHotkeySource();
        await using var engine = new DictationEngine(capture, hotkey, new FailingSpeech(10), new RecordingTextInjector(), () => []);
        hotkey.Press(); await capture.Started.Task; hotkey.Release();
        await WaitUntilAsync(() => engine.State == DictationState.AwaitingRetry);
        engine.Discard(); engine.State.ShouldBe(DictationState.Idle); engine.HasPendingAudio.ShouldBeFalse();
    }

    [Fact]
    public async Task Focus_change_preserves_text_without_insertion()
    {
        var capture = new DrainingCapture(); var hotkey = new FakeHotkeySource(); var focus = new FakeForeground();
        var injector = new RecordingTextInjector();
        await using var engine = new DictationEngine(capture, hotkey, new FailingSpeech(0), injector, () => [], foreground: focus);
        hotkey.Press(); await capture.Started.Task; focus.Current = new(2, 20); hotkey.Release();
        await WaitUntilAsync(() => engine.State == DictationState.Idle);
        injector.Injected.ShouldBeEmpty(); engine.LastResult!.Text.ShouldBe("Retained speech.");
        engine.LastResult.Delivery.ShouldBe(DeliveryOutcome.TargetChanged);
    }

    [Fact]
    public async Task Insertion_setting_applies_without_restart_and_configuration_waits_for_idle()
    {
        var capture = new DrainingCapture(); var hotkey = new FakeHotkeySource(); var enabled = true;
        var injector = new RecordingTextInjector();
        await using var engine = new DictationEngine(capture, hotkey, new FailingSpeech(0), injector, () => [], injectEnabled: () => enabled);
        hotkey.Press(); await capture.Started.Task;
        await engine.ApplyConfigurationAsync(() => { enabled = false; return Task.CompletedTask; });
        enabled.ShouldBeTrue(); hotkey.Release();
        await WaitUntilAsync(() => engine.State == DictationState.Idle);
        await engine.ApplyConfigurationAsync(() => { enabled = false; return Task.CompletedTask; });
        hotkey.Press(); hotkey.Release();
        await WaitUntilAsync(() => engine.State == DictationState.Idle);
        injector.Injected.ShouldHaveSingleItem(); engine.LastResult!.Delivery.ShouldBe(DeliveryOutcome.Disabled);
    }

    [Fact]
    public async Task Quit_cancels_loading_and_prevents_later_delivery()
    {
        var capture = new DrainingCapture(); var speech = new ControlledSpeech(); var hotkey = new FakeHotkeySource();
        var injector = new RecordingTextInjector();
        var engine = new DictationEngine(capture, hotkey, speech, injector, () => []);
        hotkey.Press(); await capture.Started.Task; await speech.LoadStarted.Task;
        await engine.DisposeAsync();
        speech.AllowLoad.TrySetResult();
        injector.Injected.ShouldBeEmpty(); engine.State.ShouldBe(DictationState.Stopping);
    }

    [Fact]
    public async Task Recording_limit_finishes_captured_audio_without_waiting_for_release()
    {
        var capture = new DrainingCapture(); var key = new FakeHotkeySource(); var injector = new RecordingTextInjector();
        await using var engine = new DictationEngine(capture, key, new FailingSpeech(0), injector, () => [],
            options: new DictationOptions { RecordingLimit = TimeSpan.FromMilliseconds(30) });
        key.Press();
        await WaitUntilAsync(() => engine.State == DictationState.Idle);
        injector.Injected.ShouldHaveSingleItem(); engine.LastResult!.AudioDuration.ShouldBeGreaterThan(TimeSpan.Zero);
    }

    [Fact]
    public async Task Failed_replacement_hook_restores_the_previous_key()
    {
        var key = new FakeHotkeySource();
        await using var engine = new DictationEngine(new DrainingCapture(), key, new FailingSpeech(0), new RecordingTextInjector(), () => []);
        engine.Start().ShouldBeTrue();
        engine.ReplaceHotkey(new BrokenKey()).ShouldBeFalse();
        key.IsRunning.ShouldBeTrue();
    }
    [Fact]
    public async Task Loading_begins_while_capture_is_active_and_release_waits_for_drain()
    {
        var capture = new DrainingCapture();
        var speech = new ControlledSpeech();
        var hotkey = new FakeHotkeySource();
        var injector = new RecordingTextInjector();
        await using var engine = new DictationEngine(capture, hotkey, speech, injector, () => []);
        hotkey.Press();
        await capture.Started.Task.WaitAsync(TimeSpan.FromSeconds(5));
        await speech.LoadStarted.Task.WaitAsync(TimeSpan.FromSeconds(2));
        engine.State.ShouldBe(DictationState.Recording);
        hotkey.Release();
        speech.AllowLoad.TrySetResult();
        await WaitUntilAsync(() => engine.State == DictationState.Idle);
        speech.Samples.ShouldBe(640);
        injector.Injected.ShouldHaveSingleItem();
    }

    internal static async Task WaitUntilAsync(Func<bool> predicate)
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        while (!predicate()) await Task.Delay(5, deadline.Token);
    }

    private sealed class DrainingCapture : IAudioCapture
    {
        public TaskCompletionSource Started { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public bool IsCapturing { get; private set; }
        public async IAsyncEnumerable<AudioChunk> CaptureAsync([EnumeratorCancellation] CancellationToken cancellationToken)
        {
            IsCapturing = true;
            yield return new AudioChunk(Enumerable.Repeat(0.5f, 320).ToArray());
            Started.TrySetResult();
            try { await Task.Delay(Timeout.Infinite, cancellationToken); }
            catch (OperationCanceledException) { }
            // Hardware may deliver its final callback during StopRecording.
            yield return new AudioChunk(Enumerable.Repeat(0.5f, 320).ToArray());
            IsCapturing = false;
        }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }

    private sealed class ControlledSpeech : ITranscriber
    {
        public TaskCompletionSource LoadStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource AllowLoad { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public bool IsReady { get; private set; }
        public int Samples { get; private set; }
        public async ValueTask<bool> LoadAsync(CancellationToken cancellationToken)
        {
            LoadStarted.TrySetResult();
            await AllowLoad.Task.WaitAsync(cancellationToken);
            IsReady = true;
            return true;
        }
        public ValueTask<string> TranscribeAsync(ReadOnlyMemory<float> samples, IReadOnlyList<string> biasPhrases, CancellationToken cancellationToken)
        {
            Samples = samples.Length;
            return ValueTask.FromResult("A complete recording.");
        }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
    private sealed class FailingSpeech(int failures) : ITranscriber
    {
        public int Calls { get; private set; }
        public bool IsReady => true;
        public ValueTask<bool> LoadAsync(CancellationToken cancellationToken) => ValueTask.FromResult(true);
        public ValueTask<string> TranscribeAsync(ReadOnlyMemory<float> samples, IReadOnlyList<string> biasPhrases, CancellationToken cancellationToken)
        {
            Calls++;
            return Calls <= failures ? ValueTask.FromException<string>(new IOException("Injected worker failure")) : ValueTask.FromResult("Retained speech.");
        }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
    private sealed class FakeForeground : IForegroundWindow
    {
        internal ForegroundTarget Current { get; set; } = new(1, 10);
        public ForegroundTarget Capture() => Current;
        public bool IsCurrent(ForegroundTarget target) => Current == target;
    }
    private sealed class BrokenKey : IHotkeySource
    {
        public event EventHandler? Pressed { add { } remove { } }
        public event EventHandler? Released { add { } remove { } }
        public bool Start() => false;
        public void StopListening() { }
        public void Dispose() { }
    }
}
