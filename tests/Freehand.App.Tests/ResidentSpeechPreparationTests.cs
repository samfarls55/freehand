using Freehand.Abstractions;
using Freehand.App;
using Xunit;

namespace Freehand.AppTests;

public sealed class ResidentSpeechPreparationTests
{
    [Fact]
    public async Task Hotkey_is_not_armed_until_the_model_is_loaded_and_residency_is_held_through_arming()
    {
        await using var speech = new PreparingSpeech();
        var armed = false;
        var preparation = ResidentSpeechPreparation.PrepareAsync(speech, () =>
        {
            Assert.True(speech.IsReady);
            Assert.Equal(1, speech.ActiveReservations);
            armed = true;
            return true;
        }, CancellationToken.None);

        Assert.False(armed);
        Assert.False(preparation.IsCompleted);
        Assert.Equal(1, speech.ActiveReservations);
        speech.Loaded.SetResult(true);

        Assert.True(await preparation);
        Assert.True(armed);
        Assert.Equal(0, speech.ActiveReservations);
        Assert.Equal(1, speech.FinishedReservations);
    }

    [Fact]
    public async Task Unavailable_model_does_not_arm_the_hotkey_and_releases_the_reservation()
    {
        await using var speech = new PreparingSpeech();
        var armed = false;
        var preparation = ResidentSpeechPreparation.PrepareAsync(speech, () => { armed = true; return true; }, CancellationToken.None);
        speech.Loaded.SetResult(false);

        Assert.False(await preparation);
        Assert.False(armed);
        Assert.Equal(0, speech.ActiveReservations);
        Assert.Equal(1, speech.FinishedReservations);
    }

    [Fact]
    public async Task Cancelling_preparation_does_not_arm_the_hotkey_and_releases_the_reservation()
    {
        await using var speech = new PreparingSpeech();
        using var cancellation = new CancellationTokenSource();
        var armed = false;
        var preparation = ResidentSpeechPreparation.PrepareAsync(speech, () => { armed = true; return true; }, cancellation.Token);
        cancellation.Cancel();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => preparation);
        Assert.False(armed);
        Assert.Equal(0, speech.ActiveReservations);
        Assert.Equal(1, speech.FinishedReservations);
    }

    private sealed class PreparingSpeech : ISpeechSession
    {
        internal TaskCompletionSource<bool> Loaded { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal int ActiveReservations { get; private set; }
        internal int FinishedReservations { get; private set; }
        public ModelState State => IsReady ? ModelState.Ready : ModelState.Loading;
        public bool IsReady { get; private set; }
        public event EventHandler? Changed { add { } remove { } }
        public ValueTask BeginWorkAsync(CancellationToken cancellationToken) { ActiveReservations++; return ValueTask.CompletedTask; }
        public void FinishWork() { ActiveReservations--; FinishedReservations++; }
        public async ValueTask<bool> LoadAsync(CancellationToken cancellationToken)
        {
            IsReady = await Loaded.Task.WaitAsync(cancellationToken);
            return IsReady;
        }
        public ValueTask<string> TranscribeAsync(ReadOnlyMemory<float> samples, IReadOnlyList<string> biasPhrases, CancellationToken cancellationToken) => ValueTask.FromResult("");
        public ValueTask ResetAsync(CancellationToken cancellationToken) => ValueTask.CompletedTask;
        public void SetIdleTimeout(TimeSpan timeout) { }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
