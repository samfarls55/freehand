using Freehand.Speech;
using Shouldly;
using Xunit;

namespace Freehand.CoreTests;

public sealed class WorkerAudioTests
{
    [Theory]
    [InlineData("prepare")]
    [InlineData("prepared")]
    public async Task Preparation_messages_have_request_identity_and_no_audio_text_or_hints(string kind)
    {
        var valid = new WorkerMessage(WorkerProtocol.Version, Guid.NewGuid(), kind);
        using var pipe = new MemoryStream();
        await WorkerProtocol.WriteAsync(pipe, valid, CancellationToken.None);
        pipe.Position = 0;
        (await WorkerProtocol.ReadAsync(pipe, CancellationToken.None)).ShouldBe(valid);
        var invalid = new[]
        {
            valid with { RequestId = Guid.Empty }, valid with { Value = "discarded text" },
            valid with { SampleCount = 1 }, valid with { ProcessId = 123 }, valid with { BiasPhrases = [] },
        };
        foreach (var message in invalid)
        {
            pipe.SetLength(0);
            pipe.Position = 0;
            await WorkerProtocol.WriteAsync(pipe, message, CancellationToken.None);
            pipe.Position = 0;
            await Should.ThrowAsync<InvalidDataException>(() => WorkerProtocol.ReadAsync(pipe, CancellationToken.None));
        }
    }

    [Fact]
    public async Task Segmented_pipe_transfer_preserves_samples_and_returns_owned_memory()
    {
        var samples = Enumerable.Range(0, 50000).Select(i => (float)Math.Sin(i * 0.01)).ToArray();
        using var pipe = new MemoryStream();
        await WorkerProtocol.WriteAudioAsync(pipe, samples.AsMemory(13, 49000), CancellationToken.None);
        pipe.Position = 0;
        var received = await WorkerProtocol.ReadAudioAsync(pipe, 49000, CancellationToken.None);
        received.ShouldBe(samples.Skip(13).Take(49000));
        // Reusing the transport buffer cannot mutate the handed-off waveform.
        pipe.Position = 0;
        await WorkerProtocol.WriteAudioAsync(pipe, new float[49000], CancellationToken.None);
        received.ShouldBe(samples.Skip(13).Take(49000));
    }

    [Theory]
    [InlineData(float.NaN)]
    [InlineData(float.PositiveInfinity)]
    [InlineData(1.01f)]
    [InlineData(-1.01f)]
    public async Task Invalid_waveforms_are_rejected(float invalid)
    {
        using var pipe = new MemoryStream();
        await WorkerProtocol.WriteAudioAsync(pipe, new[] { 0f, invalid }, CancellationToken.None);
        pipe.Position = 0;
        await Should.ThrowAsync<InvalidDataException>(() => WorkerProtocol.ReadAudioAsync(pipe, 2, CancellationToken.None));
    }

    [Fact]
    public async Task Truncated_and_oversized_waveforms_are_rejected()
    {
        using var pipe = new MemoryStream(new byte[4]);
        await Should.ThrowAsync<EndOfStreamException>(() => WorkerProtocol.ReadAudioAsync(pipe, 2, CancellationToken.None));
        await Should.ThrowAsync<InvalidDataException>(() => WorkerProtocol.ReadAudioAsync(pipe, WorkerProtocol.MaxSamples + 1, CancellationToken.None));
    }
}
