using Freehand.Abstractions;
using NAudio.Wave;
using NAudio.Wave.SampleProviders;

namespace Freehand.Platform.Windows;

/// <summary>Converts each device callback into owned mono samples without padding missing input.</summary>
internal sealed class AudioResampler
{
    private readonly BufferedWaveProvider _source;
    private readonly WdlResamplingSampleProvider _pipeline;
    private readonly float[] _pullBuffer = new float[AudioChunk.SampleRate / 10];

    internal AudioResampler(WaveFormat format)
    {
        _source = new BufferedWaveProvider(format)
        {
            BufferDuration = TimeSpan.FromSeconds(3),
            DiscardOnBufferOverflow = true,
            // Padding makes the drain loop manufacture silence forever after underrun.
            ReadFully = false,
        };
        ISampleProvider provider = _source.ToSampleProvider();
        if (format.Channels == 2)
            provider = new StereoToMonoSampleProvider(provider) { LeftVolume = 0.5f, RightVolume = 0.5f };
        else if (format.Channels > 2) provider = new DownmixSampleProvider(provider);
        _pipeline = new WdlResamplingSampleProvider(provider, AudioChunk.SampleRate);
    }

    internal IEnumerable<float[]> Convert(byte[] input, int count)
    {
        _source.AddSamples(input, 0, count);
        while (true)
        {
            var read = _pipeline.Read(_pullBuffer, 0, _pullBuffer.Length);
            if (read == 0) yield break;
            // NAudio owns and reuses its callback buffer; the engine owns this copy.
            var owned = new float[read];
            Array.Copy(_pullBuffer, owned, read);
            yield return owned;
        }
    }
}
