using System.Threading.Channels;
using Freehand.Platform.Windows;
using Xunit;

namespace Freehand.Windows.Tests;

public sealed class HotkeyTests
{
    [Theory]
    [InlineData(0x03)]
    [InlineData(0x41)]
    [InlineData(0x09)]
    [InlineData(0x1B)]
    [InlineData(0x20)]
    [InlineData(0x5B)]
    [InlineData(0x87)]
    [InlineData(0xA3)]
    [InlineData(0xB3)]
    [InlineData(0xBA)]
    public void Single_keys_activate_once_per_hold(int key)
    {
        var state = new HotkeyState([key]);
        Assert.True(state.Update(key, true).Active);
        Assert.Null(state.Update(key, true).Active);
        Assert.False(state.Update(key, false).Active);
        Assert.Null(state.Update(key, false).Active);
        Assert.True(state.Update(key, true).Active);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Chords_require_all_keys_and_release_when_any_member_is_released(bool reverse)
    {
        int[] chord = [0xA2, 0xA1, 0x41, 0x42];
        var state = new HotkeyState(chord);
        var order = reverse ? chord.Reverse().ToArray() : chord;
        foreach (var key in order[..^1]) Assert.Null(state.Update(key, true).Active);
        Assert.True(state.Update(order[^1], true).Active);
        Assert.Null(state.Update(order[^1], true).Active);
        Assert.Null(state.Update(0x58, true).Active);
        Assert.Null(state.Update(0x58, false).Active);
        Assert.False(state.Update(order[1], false).Active);
        Assert.True(state.Update(order[1], true).Active);
        Assert.False(state.Update(order[^1], false).Active);
    }

    [Fact]
    public void Recording_uses_simultaneous_keys_and_waits_for_every_release()
    {
        var state = new HotkeyState([0xA3]);
        state.BeginCapture();
        Assert.Equal([0x41], Assert.IsType<int[]>(state.Update(0x41, true).CapturedKeys));
        Assert.Equal([0x41, 0xA3], Assert.IsType<int[]>(state.Update(0xA3, true).CapturedKeys));
        Assert.False(state.Update(0x41, false).Complete);
        var complete = state.Update(0xA3, false);
        Assert.True(complete.Complete);
        Assert.Equal([0x41, 0xA3], Assert.IsType<int[]>(complete.CapturedKeys));
        state.EndCapture();
        Assert.True(state.Update(0xA3, true).Active);
    }

    [Fact]
    public void Recording_does_not_include_keys_held_when_editor_opens()
    {
        var state = new HotkeyState([0xA3]);
        state.Update(0x0D, true); state.BeginCapture();
        Assert.Null(state.Update(0x0D, false).CapturedKeys);
        Assert.False(state.Update(0x09, true).Complete);
        var complete = state.Update(0x09, false);
        Assert.Equal([0x09], Assert.IsType<int[]>(complete.CapturedKeys)); Assert.True(complete.Complete);
    }

    [Fact]
    public void Cancelling_with_the_old_binding_held_waits_for_release_before_rearming()
    {
        var state = new HotkeyState([0xA3]);
        state.BeginCapture(); state.Update(0xA3, true); state.EndCapture();
        Assert.Null(state.Update(0x41, true).Active);
        Assert.Null(state.Update(0x41, false).Active);
        Assert.Null(state.Update(0xA3, false).Active);
        Assert.True(state.Update(0xA3, true).Active);
    }

    [Fact]
    public async Task Hook_normalizes_modifier_sides_and_ignores_its_own_injected_text()
    {
        using var hook = new PushToTalkHook([0xA3, 0x41]);
        var events = Channel.CreateUnbounded<bool>();
        hook.Pressed += (_, _) => events.Writer.TryWrite(true);
        hook.Released += (_, _) => events.Writer.TryWrite(false);
        hook.ProcessKey(0x11, 0x1D, 0, true); // Left Ctrl does not match Right Ctrl.
        hook.ProcessKey(0x11, 0x1D, 1, true);
        hook.ProcessKey(0x41, 0, 0, true, PushToTalkHook.InjectedTag);
        hook.ProcessKey(0x41, 0, 0, true);
        hook.ProcessKey(0x41, 0, 0, true);
        hook.ProcessKey(0x11, 0x1D, 1, false);
        Assert.True(await events.Reader.ReadAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.False(await events.Reader.ReadAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.False(events.Reader.TryRead(out _));
    }

    [Theory]
    [InlineData(0x10, 0x36, 0, 0xA1)]
    [InlineData(0x10, 0x2A, 0, 0xA0)]
    [InlineData(0x12, 0x38, 1, 0xA5)]
    [InlineData(0x12, 0x38, 0, 0xA4)]
    public async Task Hook_distinguishes_both_sides_of_shift_and_alt(int rawKey, int scan, uint flags, int key)
    {
        using var hook = new PushToTalkHook([key], static () => { });
        var pressed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        hook.Pressed += (_, _) => pressed.TrySetResult();
        hook.ProcessKey(rawKey, scan, flags, true);
        await pressed.Task.WaitAsync(TimeSpan.FromSeconds(5));
    }

    [Fact]
    public async Task Native_recorder_pauses_dictation_and_cancellation_restores_it()
    {
        using var hook = new PushToTalkHook();
        var events = Channel.CreateUnbounded<bool>();
        hook.Pressed += (_, _) => events.Writer.TryWrite(true);
        hook.Released += (_, _) => events.Writer.TryWrite(false);
        var progress = new CapturedProgress();
        var recording = hook.RecordAsync(progress, CancellationToken.None);
        hook.ProcessKey(0xA3, 0, 0, true);
        hook.ProcessKey(0x09, 0, 0, true);
        hook.ProcessKey(0x09, 0, 0, false);
        hook.ProcessKey(0xA3, 0, 0, false);
        Assert.Equal([0x09, 0xA3], await recording.WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.False(events.Reader.TryRead(out _));
        using var cancel = new CancellationTokenSource();
        recording = hook.RecordAsync(progress, cancel.Token);
        cancel.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => recording);
        hook.ProcessKey(0xA3, 0, 0, true); hook.ProcessKey(0xA3, 0, 0, false);
        Assert.True(await events.Reader.ReadAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.False(await events.Reader.ReadAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(5)));
    }

    private sealed class CapturedProgress : IProgress<IReadOnlyList<int>>
    {
        public void Report(IReadOnlyList<int> value) { }
    }
}
