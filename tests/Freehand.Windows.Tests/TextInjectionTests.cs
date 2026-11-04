using Freehand.Abstractions;
using Freehand.Platform.Windows;
using Xunit;
using Input = Freehand.Platform.Windows.SendInputTextInjector.INPUT;

namespace Freehand.Windows.Tests;

public sealed class TextInjectionTests
{
    private static readonly ForegroundTarget Target = new((nint)1, 2);

    [Fact]
    public async Task Partial_batch_releases_its_last_key_without_replaying_the_prefix_or_suffix()
    {
        var calls = new List<Input[]>();
        var injector = new SendInputTextInjector(_ => true, () => false, inputs =>
        {
            calls.Add(inputs);
            return calls.Count == 1 ? 3u : (uint)inputs.Length;
        }, _ => { });

        Assert.Equal(DeliveryOutcome.PartialOrUncertain,
            await injector.InjectAsync("a rest of the transcript", Target, CancellationToken.None));
        Assert.Equal(2, calls.Count);
        var release = Assert.Single(calls[1]);
        Assert.Equal(' ', (char)release.Union.Keyboard.ScanCode);
        Assert.Equal(6u, release.Union.Keyboard.Flags); // Unicode key-up, not another space-down.
    }

    [Fact]
    public async Task A_rejected_batch_does_not_invent_a_release_or_retry_text()
    {
        var calls = 0;
        var injector = new SendInputTextInjector(_ => true, () => false, _ => { calls++; return 0; }, _ => { });
        Assert.Equal(DeliveryOutcome.PartialOrUncertain,
            await injector.InjectAsync("complete text", Target, CancellationToken.None));
        Assert.Equal(1, calls);
    }

    [Fact]
    public async Task Delivery_waits_for_the_physical_modifier_to_be_released()
    {
        var held = true;
        var pauses = 0;
        var delivered = new List<Input>();
        var injector = new SendInputTextInjector(_ => true, () => held, inputs =>
        {
            Assert.False(held);
            delivered.AddRange(inputs); return (uint)inputs.Length;
        }, _ => { pauses++; held = false; });
        Assert.Equal(DeliveryOutcome.Delivered,
            await injector.InjectAsync("Not a Ctrl shortcut", Target, CancellationToken.None));
        Assert.Equal(1, pauses);
        Assert.Equal("Not a Ctrl shortcut", Decode(delivered));
    }

    [Fact]
    public async Task Pressing_a_modifier_during_delivery_stops_before_the_next_batch()
    {
        var held = false;
        var delivered = new List<Input>();
        var injector = new SendInputTextInjector(_ => true, () => held, inputs =>
        {
            delivered.AddRange(inputs); return (uint)inputs.Length;
        }, _ => held = true);
        Assert.Equal(DeliveryOutcome.PartialOrUncertain,
            await injector.InjectAsync(new string('x', 100), Target, CancellationToken.None));
        Assert.InRange(Decode(delivered).Length, 1, 32);
    }

    [Fact]
    public async Task Focus_change_while_waiting_does_not_type_into_either_window()
    {
        var current = true;
        var injector = new SendInputTextInjector(_ => current, () => true,
            _ => throw new InvalidOperationException("Must not type while Ctrl is held"), _ => current = false);
        Assert.Equal(DeliveryOutcome.TargetChanged,
            await injector.InjectAsync("Do not send", Target, CancellationToken.None));
    }

    [Fact]
    public async Task Paced_batches_preserve_all_text_spaces_and_surrogate_pairs()
    {
        var text = new string('x', 31) + "🙂" + new string(' ', 7) + string.Concat(Enumerable.Repeat("Full transcript. ", 30));
        var received = new List<Input>();
        var pauses = 0;
        var injector = new SendInputTextInjector(_ => true, () => false, inputs =>
        {
            Assert.InRange(inputs.Length, 2, 66);
            var batch = Decode(inputs);
            Assert.False(char.IsHighSurrogate(batch[^1]));
            Assert.False(char.IsLowSurrogate(batch[0]));
            received.AddRange(inputs); return (uint)inputs.Length;
        }, _ => pauses++);
        Assert.Equal(DeliveryOutcome.Delivered,
            await injector.InjectAsync(text, Target, CancellationToken.None));
        Assert.Equal(text, Decode(received));
        Assert.True(pauses > 0);
    }

    [Fact]
    public async Task Cancellation_between_batches_never_replays_or_sends_the_remainder()
    {
        using var cancellation = new CancellationTokenSource();
        var calls = 0;
        var injector = new SendInputTextInjector(_ => true, () => false,
            inputs => { calls++; return (uint)inputs.Length; }, _ => cancellation.Cancel());
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            injector.InjectAsync(new string('x', 100), Target, cancellation.Token).AsTask());
        Assert.Equal(1, calls);
    }

    [Theory]
    [InlineData("line one\rline two")]
    [InlineData("line one\r\nline two")]
    [InlineData("line one\nline two")]
    public async Task Every_newline_form_emits_one_balanced_Return(string text)
    {
        var received = new List<Input>();
        var injector = new SendInputTextInjector(_ => true, () => false, inputs =>
        {
            received.AddRange(inputs); return (uint)inputs.Length;
        }, _ => { });
        Assert.Equal(DeliveryOutcome.Delivered, await injector.InjectAsync(text, Target, CancellationToken.None));
        var enter = received.Where(input => input.Union.Keyboard.VirtualKey == 0x0D).ToArray();
        Assert.Equal(2, enter.Length);
        Assert.Equal(0u, enter[0].Union.Keyboard.Flags & 2);
        Assert.Equal(2u, enter[1].Union.Keyboard.Flags & 2);
        Assert.DoesNotContain(received, input => input.Union.Keyboard.VirtualKey == 0 && input.Union.Keyboard.ScanCode == '\r');
    }

    [Fact]
    public async Task Partial_Return_is_released_without_typing_the_following_line()
    {
        var calls = new List<Input[]>();
        var injector = new SendInputTextInjector(_ => true, () => false, inputs =>
        {
            calls.Add(inputs);
            return calls.Count == 2 ? 1u : (uint)inputs.Length;
        }, _ => { });
        Assert.Equal(DeliveryOutcome.PartialOrUncertain,
            await injector.InjectAsync("first\nsecond", Target, CancellationToken.None));
        Assert.Equal(3, calls.Count);
        var release = Assert.Single(calls[2]);
        Assert.Equal(0x0D, release.Union.Keyboard.VirtualKey);
        Assert.Equal(2u, release.Union.Keyboard.Flags & 2);
        Assert.Equal("first", Decode(calls.SelectMany(inputs => inputs)));
    }

    private static string Decode(IEnumerable<Input> inputs) => new(inputs
        .Where(input => (input.Union.Keyboard.Flags & 2) == 0 && input.Union.Keyboard.VirtualKey == 0)
        .Select(input => (char)input.Union.Keyboard.ScanCode).ToArray());
}

[CollectionDefinition("Native text delivery", DisableParallelization = true)]
public sealed class NativeTextDeliveryGroup;

[Collection("Native text delivery")]
public sealed class NativeTextDeliveryTests
{
    [Fact]
    public async Task Real_SendInput_preserves_complete_multiline_Unicode_text_in_a_Windows_edit_control()
    {
        using var field = new WindowsDeliveryProbe();
        var target = field.BeginTrial();
        var text = new string('x', 31) + "🙂 café 日本語\r\n" +
            string.Concat(Enumerable.Repeat("Complete text with  double spaces. ", 60)) + "End. ";
        var injector = new SendInputTextInjector();
        Assert.Equal(DeliveryOutcome.Delivered, await injector.InjectAsync(text, target, CancellationToken.None));
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        while (field.ReadText() != text && !deadline.IsCancellationRequested) await Task.Delay(20);
        Assert.Equal(text, field.ReadText());
    }
}
