using Freehand.Speech;
using Shouldly;
using Xunit;

namespace Freehand.CoreTests;

public sealed class WorkerAudioTests
{
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
