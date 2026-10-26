using System.Threading.Channels;
using Freehand.Platform.Windows;
using Xunit;

namespace Freehand.Windows.Tests;

public sealed class ModifierMenuTests
{
    [Theory]
    [InlineData(0x5B, false, false)]
    [InlineData(0x5B, false, true)]
    [InlineData(0x5B, true, false)]
    [InlineData(0x5B, true, true)]
    [InlineData(0x5C, false, false)]
    [InlineData(0x5C, false, true)]
    [InlineData(0x5C, true, false)]
    [InlineData(0x5C, true, true)]
    [InlineData(0xA4, false, false)]
    [InlineData(0xA4, false, true)]
    [InlineData(0xA4, true, false)]
    [InlineData(0xA4, true, true)]
    [InlineData(0xA5, false, false)]
    [InlineData(0xA5, false, true)]
    [InlineData(0xA5, true, false)]
    [InlineData(0xA5, true, true)]
    public async Task Menu_is_masked_through_final_release_in_either_press_and_release_order(int modifier, bool modifierFirst, bool modifierReleasedFirst)
    {
        var masks = 0;
        var events = Channel.CreateUnbounded<bool>();
        using var hook = new PushToTalkHook([0xA2, modifier], () => masks++);
        hook.Pressed += (_, _) => events.Writer.TryWrite(true);
        hook.Released += (_, _) => events.Writer.TryWrite(false);
        var first = modifierFirst ? modifier : 0xA2;
        var last = modifierFirst ? 0xA2 : modifier;

        hook.ProcessKey(first, 0, 0, true);
        Assert.False(events.Reader.TryRead(out _));
        hook.ProcessKey(last, 0, 0, true);
        Assert.Equal(1, masks); // Masking is synchronous, before the press is dispatched.
        hook.ProcessKey(last, 0, 0, true); // Auto-repeat must not mask or start twice.
        Assert.Equal(1, masks);
        hook.ProcessKey(modifierReleasedFirst ? modifier : 0xA2, 0, 0, false);
        if (!modifierReleasedFirst) hook.ProcessKey(modifier, 0, 0, true); // Windows can repeat after Ctrl is up.
        hook.ProcessKey(modifierReleasedFirst ? 0xA2 : modifier, 0, 0, false);
        Assert.Equal(2, masks); // The final menu-key up is masked before it reaches Windows.

        Assert.True(await NextAsync(events.Reader));
        Assert.False(await NextAsync(events.Reader));
        Assert.False(events.Reader.TryRead(out _));

        // Both keys rearm after release; no modifier remains stuck in the tracker.
        hook.ProcessKey(first, 0, 0, true); hook.ProcessKey(last, 0, 0, true);
        hook.ProcessKey(first, 0, 0, false); hook.ProcessKey(last, 0, 0, false);
        Assert.Equal(4, masks);
        Assert.True(await NextAsync(events.Reader));
        Assert.False(await NextAsync(events.Reader));
        Assert.False(events.Reader.TryRead(out _));
    }

    [Theory]
    [InlineData(0x5B)]
    [InlineData(0x5C)]
    [InlineData(0xA4)]
    [InlineData(0xA5)]
    public void A_menu_modifier_can_be_the_entire_shortcut(int modifier)
    {
        var state = new HotkeyState([modifier]);
        var press = state.Update(modifier, true);
        Assert.True(press.Active); Assert.True(press.MaskModifierMenu);
        Assert.False(state.Update(modifier, true).MaskModifierMenu);
        var release = state.Update(modifier, false);
        Assert.False(release.Active); Assert.True(release.MaskModifierMenu);
    }

    [Theory]
    [InlineData(0xA3)]
    [InlineData(0x7C)]
    public void Existing_shortcuts_do_not_mask_unrelated_Windows_or_Alt_keys(int trigger)
    {
        var state = new HotkeyState([trigger]);
        foreach (var key in new[] { 0x5B, 0x45, 0xA4 })
        {
            Assert.False(state.Update(key, true).MaskModifierMenu);
            Assert.False(state.Update(key, false).MaskModifierMenu);
        }
        // Even while an unrelated Windows key is held, the saved trigger passes through.
        state.Update(0x5B, true);
        var press = state.Update(trigger, true);
        Assert.True(press.Active); Assert.False(press.MaskModifierMenu);
        Assert.False(state.Update(trigger, false).MaskModifierMenu);
        Assert.False(state.Update(0x5B, false).MaskModifierMenu);
    }

    [Theory]
    [InlineData(0x5B)]
    [InlineData(0x5C)]
    public void An_incomplete_Ctrl_Windows_shortcut_preserves_Start_and_other_Windows_shortcuts(int modifier)
    {
        var state = new HotkeyState([0xA2, modifier]);
        Assert.False(state.Update(modifier, true).MaskModifierMenu);
        Assert.False(state.Update(0x45, true).MaskModifierMenu);
        Assert.False(state.Update(0x45, false).MaskModifierMenu);
        Assert.False(state.Update(modifier, false).MaskModifierMenu);
    }

    [Theory]
    [InlineData(0x5B)]
    [InlineData(0x5C)]
    [InlineData(0xA4)]
    [InlineData(0xA5)]
    public async Task Recording_a_shortcut_masks_menus_without_recording_the_mask_key(int modifier)
    {
        var masks = 0;
        PushToTalkHook? hook = null;
        using var ownedHook = new PushToTalkHook([0xA3], () =>
        {
            masks++;
            hook!.ProcessKey(0xE8, 0, 0, true, PushToTalkHook.InjectedTag);
            hook.ProcessKey(0xE8, 0, 0, false, PushToTalkHook.InjectedTag);
        });
        hook = ownedHook;
        var recording = hook.RecordAsync(new CapturedProgress(), CancellationToken.None);
        hook.ProcessKey(modifier, 0, 0, true);
        hook.ProcessKey(0xA2, 0, 0, true);
        hook.ProcessKey(0xA2, 0, 0, false);
        hook.ProcessKey(modifier, 0, 0, false);
        Assert.Equal(new[] { modifier, 0xA2 }.Order(), await recording.WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.Equal(3, masks);
    }

    [Fact]
    public async Task Cancelling_capture_with_Windows_held_does_not_mask_future_unrelated_shortcuts()
    {
        var masks = 0;
        using var hook = new PushToTalkHook([0xA3], () => masks++);
        using var cancel = new CancellationTokenSource();
        var recording = hook.RecordAsync(new CapturedProgress(), cancel.Token);
        hook.ProcessKey(0x5B, 0, 0, true);
        cancel.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => recording);
        hook.ProcessKey(0x5B, 0, 0, false);
        hook.ProcessKey(0x5B, 0, 0, true); hook.ProcessKey(0x5B, 0, 0, false);
        Assert.Equal(2, masks);
    }

    private static async Task<bool> NextAsync(ChannelReader<bool> reader) =>
        await reader.ReadAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(5));

    private sealed class CapturedProgress : IProgress<IReadOnlyList<int>>
    {
        public void Report(IReadOnlyList<int> value) { }
    }
}
