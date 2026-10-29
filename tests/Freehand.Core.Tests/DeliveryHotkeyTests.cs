using Freehand.Abstractions;
using Freehand.Core;
using Freehand.Testing;
using Shouldly;
using Xunit;

namespace Freehand.CoreTests;

public sealed class DeliveryHotkeyTests
{
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Delivery_pauses_only_an_eligible_hook_and_restores_it(bool canPause)
    {
        var key = new DeliveryKey { CanPause = canPause };
        var injector = new CheckingInjector(key);
        await using var engine = new DictationEngine(FakeAudioCapture.Tone(0.4), key,
            new FakeTranscriber("Keep the full text."), injector, () => []);
        engine.Start().ShouldBeTrue();
        await DictateAsync(key, engine);
        key.PauseCalls.ShouldBe(1);
        injector.ObservedPaused.ShouldBe(canPause);
        injector.Calls.ShouldBe(1);
        key.Starts.ShouldBe(canPause ? 2 : 1);
        key.Listening.ShouldBeTrue();
        engine.LastResult!.Delivery.ShouldBe(DeliveryOutcome.Delivered);
    }

    [Fact]
    public async Task Failed_delivery_still_restores_the_hook_without_sending_again()
    {
        var key = new DeliveryKey();
        var injector = new CheckingInjector(key) { Fail = true };
        await using var engine = new DictationEngine(FakeAudioCapture.Tone(0.4), key,
            new FakeTranscriber("Keep the full text."), injector, () => []);
        engine.Start().ShouldBeTrue();
        await DictateAsync(key, engine);
        key.Starts.ShouldBe(2);
        key.Listening.ShouldBeTrue();
        injector.Calls.ShouldBe(1);
        engine.LastResult!.Delivery.ShouldBe(DeliveryOutcome.PartialOrUncertain);
        engine.LastResult.Text.ShouldBe("Keep the full text.");
    }

    [Fact]
    public async Task A_failed_hook_restart_is_reported_and_can_be_retried()
    {
        var key = new DeliveryKey { FailRestart = true };
        var injector = new CheckingInjector(key);
        await using var engine = new DictationEngine(FakeAudioCapture.Tone(0.4), key,
            new FakeTranscriber("Keep the full text."), injector, () => []);
        engine.Start().ShouldBeTrue();
        await DictateAsync(key, engine);
        injector.Calls.ShouldBe(1);
        engine.LastResult!.Delivery.ShouldBe(DeliveryOutcome.Delivered);
        engine.Feedback!.Outcome.ShouldBe(DictationOutcome.CaptureFailure);
        key.FailRestart = false;
        engine.RefreshReadiness().ShouldBeTrue();
        key.Listening.ShouldBeTrue();
    }

    [Fact]
    public async Task Quit_during_delivery_does_not_restart_a_disposed_hook()
    {
        var key = new DeliveryKey();
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var injector = new HoldingInjector(entered);
        var engine = new DictationEngine(FakeAudioCapture.Tone(0.4), key,
            new FakeTranscriber("Keep the full text."), injector, () => []);
        engine.Start().ShouldBeTrue();
        await ReleaseAfterCaptureAsync(key, engine);
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        await engine.DisposeAsync();
        key.Starts.ShouldBe(1);
        key.Listening.ShouldBeFalse();
    }

    private static async Task DictateAsync(DeliveryKey key, DictationEngine engine)
    {
        await ReleaseAfterCaptureAsync(key, engine);
        await LifecycleTests.WaitUntilAsync(() => engine.State == DictationState.Idle);
    }

    private static async Task ReleaseAfterCaptureAsync(DeliveryKey key, DictationEngine engine)
    {
        var captured = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        void OnChanged(object? sender, EventArgs args)
        {
            if (engine.Level > 0) captured.TrySetResult();
        }
        engine.Changed += OnChanged;
        try
        {
            key.Press();
            await captured.Task.WaitAsync(TimeSpan.FromSeconds(5));
            key.Release();
        }
        finally { engine.Changed -= OnChanged; }
    }

    private sealed class DeliveryKey : ITextDeliveryHotkeySource
    {
        public event EventHandler? Pressed;
        public event EventHandler? Released;
        internal bool CanPause { get; init; } = true;
        internal bool FailRestart { get; set; }
        internal bool Listening { get; private set; }
        internal int Starts { get; private set; }
        internal int PauseCalls { get; private set; }
        public bool Start() { Starts++; Listening = !FailRestart || Starts == 1; return Listening; }
        public void StopListening() => Listening = false;
        public void Dispose() => StopListening();
        public ValueTask<bool> TryPauseForDeliveryAsync(CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            PauseCalls++;
            if (CanPause) Listening = false;
            return ValueTask.FromResult(CanPause);
        }
        internal void Press() => Pressed?.Invoke(this, EventArgs.Empty);
        internal void Release() => Released?.Invoke(this, EventArgs.Empty);
    }

    private sealed class CheckingInjector(DeliveryKey key) : ITextInjector
    {
        internal bool Fail { get; init; }
        internal bool ObservedPaused { get; private set; }
        internal int Calls { get; private set; }
        public ValueTask<bool> InjectAsync(string text, CancellationToken cancellationToken)
        {
            ObservedPaused = !key.Listening; Calls++;
            return ValueTask.FromResult(!Fail);
        }
    }

    private sealed class HoldingInjector(TaskCompletionSource entered) : ITextInjector
    {
        public async ValueTask<bool> InjectAsync(string text, CancellationToken cancellationToken)
        {
            entered.TrySetResult();
            await Task.Delay(Timeout.Infinite, cancellationToken);
            return true;
        }
    }
}
