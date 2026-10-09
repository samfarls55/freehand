using System.Buffers.Binary;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using Freehand.Abstractions;

namespace Freehand.Speech;

/// <summary>Named deadlines for measurements and later tuning.</summary>
public sealed record WorkerOptions
{
    /// <summary>Process connection and model load deadline.</summary>
    public TimeSpan StartupTimeout { get; init; } = TimeSpan.FromSeconds(30);
    /// <summary>Deadline for each segment, always at most sixty seconds of audio.</summary>
    public TimeSpan InferenceTimeout { get; init; } = TimeSpan.FromSeconds(60);
    /// <summary>Graceful process shutdown deadline.</summary>
    public TimeSpan ShutdownTimeout { get; init; } = TimeSpan.FromSeconds(5);
    /// <summary>Default model idle interval.</summary>
    public TimeSpan IdleTimeout { get; init; } = TimeSpan.FromMinutes(5);
}
internal sealed record WorkerMessage(int Version, Guid RequestId, string Kind, string? Value = null, int SampleCount = 0, int ProcessId = 0);
internal static class WorkerProtocol
{
    internal const int Version = 1;
    internal const int MaxSamples = 60 * AudioChunk.SampleRate;
    internal static async Task WriteAsync(Stream stream, WorkerMessage message, CancellationToken token)
    {
        var bytes = JsonSerializer.SerializeToUtf8Bytes(message, WorkerJsonContext.Default.WorkerMessage);
        var header = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(header, bytes.Length);
        await stream.WriteAsync(header, token).ConfigureAwait(false);
        await stream.WriteAsync(bytes, token).ConfigureAwait(false);
        await stream.FlushAsync(token).ConfigureAwait(false);
    }
    internal static async Task<WorkerMessage> ReadAsync(Stream stream, CancellationToken token)
    {
        var header = new byte[4]; await stream.ReadExactlyAsync(header, token).ConfigureAwait(false);
        var size = BinaryPrimitives.ReadInt32LittleEndian(header);
        if (size is < 1 or > 1048576) throw new InvalidDataException("Invalid message length");
        var body = new byte[size]; await stream.ReadExactlyAsync(body, token).ConfigureAwait(false);
        var message = JsonSerializer.Deserialize(body, WorkerJsonContext.Default.WorkerMessage) ?? throw new InvalidDataException("Empty message");
        if (message.Version != Version) throw new InvalidDataException("Unsupported protocol version");
        return message;
    }
    internal static async Task WriteAudioAsync(Stream stream, ReadOnlyMemory<float> samples, CancellationToken token)
    {
        if (samples.Length > MaxSamples) throw new InvalidDataException("Segment exceeds sixty seconds");
        var bytes = MemoryMarshal.AsBytes(samples.Span).ToArray();
        await stream.WriteAsync(bytes, token).ConfigureAwait(false);
        await stream.FlushAsync(token).ConfigureAwait(false);
    }
    internal static async Task<float[]> ReadAudioAsync(Stream stream, int count, CancellationToken token)
    {
        if (count is < 1 or > MaxSamples) throw new InvalidDataException("Invalid sample count");
        var bytes = new byte[count * sizeof(float)]; await stream.ReadExactlyAsync(bytes, token).ConfigureAwait(false);
        var audio = MemoryMarshal.Cast<byte, float>(bytes).ToArray();
        foreach (var sample in audio) if (!float.IsFinite(sample) || sample is < -1 or > 1) throw new InvalidDataException("Invalid audio");
        return audio;
    }
}
[JsonSerializable(typeof(WorkerMessage))]
internal sealed partial class WorkerJsonContext : JsonSerializerContext;
