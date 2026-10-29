using Freehand.Platform.Windows;
using Xunit;

namespace Freehand.Windows.Tests;

public sealed class DeliveryPauseTests
{
    [Fact]
    public void A_released_Right_Ctrl_allows_delivery_pause()
    {
        var state = new HotkeyState([0xA3]);
        Assert.True(state.CanPauseForDelivery);
        state.Update(0xA3, true);
        Assert.False(state.CanPauseForDelivery);
        state.Update(0xA3, false);
        Assert.True(state.CanPauseForDelivery);
    }

    [Theory]
    [InlineData(0x5B)]
    [InlineData(0x5C)]
    [InlineData(0xA4)]
    [InlineData(0xA5)]
    public void A_menu_modifier_must_receive_its_final_mask_before_delivery_pause(int modifier)
    {
        var state = new HotkeyState([0xA2, modifier]);
        state.Update(modifier, true); state.Update(0xA2, true);
        state.Update(0xA2, false);
        Assert.False(state.CanPauseForDelivery);
        state.Update(modifier, true);
        Assert.False(state.CanPauseForDelivery);
        Assert.True(state.Update(modifier, false).MaskModifierMenu);
        Assert.True(state.CanPauseForDelivery);
    }

    [Fact]
    public void Shortcut_capture_blocks_delivery_pause_until_capture_ends()
    {
        var state = new HotkeyState([0xA3]);
        state.BeginCapture();
        Assert.False(state.CanPauseForDelivery);
        state.Update(0x41, true); state.Update(0x41, false);
        Assert.False(state.CanPauseForDelivery);
        state.EndCapture();
        Assert.True(state.CanPauseForDelivery);
    }

    [Fact]
    public void An_unrelated_held_key_blocks_delivery_pause()
    {
        var state = new HotkeyState([0xA3]);
        state.Update(0x41, true);
        Assert.False(state.CanPauseForDelivery);
        state.Update(0x41, false);
        Assert.True(state.CanPauseForDelivery);
    }

    [Fact]
    public async Task Native_pause_preserves_menu_tracking_and_restores_listening()
    {
        var masks = 0;
        using var hook = new PushToTalkHook([0xA2, 0x5B], () => masks++);
        Assert.True(hook.Start());
        hook.ProcessKey(0x5B, 0, 0, true); hook.ProcessKey(0xA2, 0, 0, true);
        hook.ProcessKey(0xA2, 0, 0, false);
        Assert.False(await hook.TryPauseForDeliveryAsync(CancellationToken.None).AsTask().WaitAsync(TimeSpan.FromSeconds(5)));
        hook.ProcessKey(0x5B, 0, 0, true);
        Assert.False(await hook.TryPauseForDeliveryAsync(CancellationToken.None).AsTask().WaitAsync(TimeSpan.FromSeconds(5)));
        hook.ProcessKey(0x5B, 0, 0, false);
        Assert.Equal(2, masks);
        Assert.True(await hook.TryPauseForDeliveryAsync(CancellationToken.None).AsTask().WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.False(await hook.TryPauseForDeliveryAsync(CancellationToken.None));
        Assert.True(hook.Start());
        Assert.True(await hook.TryPauseForDeliveryAsync(CancellationToken.None).AsTask().WaitAsync(TimeSpan.FromSeconds(5)));
    }

    [Fact]
    public async Task Stopping_the_hook_completes_a_concurrent_pause_request()
    {
        using var hook = new PushToTalkHook();
        Assert.True(hook.Start());
        var pause = hook.TryPauseForDeliveryAsync(CancellationToken.None).AsTask();
        hook.StopListening();
        await pause.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.False(await hook.TryPauseForDeliveryAsync(CancellationToken.None));
        Assert.True(hook.Start());
        Assert.True(await hook.TryPauseForDeliveryAsync(CancellationToken.None).AsTask().WaitAsync(TimeSpan.FromSeconds(5)));
    }

    [Fact]
    public async Task A_cancelled_pause_does_not_disable_listening()
    {
        using var hook = new PushToTalkHook();
        Assert.True(hook.Start());
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => hook.TryPauseForDeliveryAsync(cancellation.Token).AsTask());
        Assert.True(await hook.TryPauseForDeliveryAsync(CancellationToken.None).AsTask().WaitAsync(TimeSpan.FromSeconds(5)));
    }
}
