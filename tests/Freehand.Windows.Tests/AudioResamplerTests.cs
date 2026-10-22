using System.Runtime.InteropServices;
using Freehand.Platform.Windows;
using NAudio.Wave;
using Xunit;

namespace Freehand.Windows.Tests;

public sealed class AudioResamplerTests
{
    [Theory]
    [InlineData(48000, 1, 32)]
    [InlineData(48000, 2, 32)]
    [InlineData(48000, 4, 32)]
    [InlineData(16000, 1, 16)]
    public void One_callback_stops_at_the_end_of_its_audio_and_later_callbacks_resume(int rate, int channels, int bits)
    {
        var format = bits == 32 ? WaveFormat.CreateIeeeFloatWaveFormat(rate, channels) : new WaveFormat(rate, bits, channels);
        var converter = new AudioResampler(format);
        var count = rate / 20 * channels;
        var bytes = bits == 32
            ? MemoryMarshal.AsBytes(Enumerable.Repeat(0.25f, count).ToArray().AsSpan()).ToArray()
            : MemoryMarshal.AsBytes(Enumerable.Repeat((short)8192, count).ToArray().AsSpan()).ToArray();
        var total = 0;
        float[]? first = null;
        for (var callback = 0; callback < 20; callback++)
        {
            // A finite guard catches a padding loop without hanging the test runner.
            var chunks = converter.Convert(bytes, bytes.Length).Take(20).ToArray();
            Assert.InRange(chunks.Length, 1, 2);
            var outputCount = chunks.Sum(chunk => chunk.Length);
            Assert.InRange(outputCount, 1, 850);
            first ??= chunks[0];
            total += outputCount;
        }
        Assert.InRange(total, 15900, 16000);
        var before = first!.ToArray();
        Array.Clear(bytes);
        _ = converter.Convert(bytes, bytes.Length).Take(20).ToArray();
        Assert.Equal(before, first);
    }
}
