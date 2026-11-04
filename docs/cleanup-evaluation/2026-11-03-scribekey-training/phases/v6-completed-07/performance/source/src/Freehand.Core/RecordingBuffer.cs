using Freehand.Abstractions;

namespace Freehand.Core;

/// <summary>Retains one recording as owned segments, ready for decoding as capture continues.</summary>
internal sealed class RecordingBuffer(int maxSegmentSeconds, Action<ReadOnlyMemory<float>> segmentReady)
{
    private readonly List<ReadOnlyMemory<float>> _pending = [];
    private readonly List<ReadOnlyMemory<float>> _segments = [];
    private int _pendingSamples;
    private double _energy;
    private readonly int _segmentSamples = maxSegmentSeconds * AudioChunk.SampleRate;

    internal int Count { get; private set; }
    internal bool IsSilent => Count == 0 || Math.Sqrt(_energy / Count) < 0.00001;
    internal IReadOnlyList<ReadOnlyMemory<float>> Segments => _segments;

    internal void Append(ReadOnlyMemory<float> samples)
    {
        if (samples.IsEmpty) return;
        // Capture transfers ownership. Keep the original memory until it is segmented.
        _pending.Add(samples);
        Count += samples.Length;
        _pendingSamples += samples.Length;
        foreach (var sample in samples.Span) _energy += (double)sample * sample;
        while (_pendingSamples > _segmentSamples)
        {
            var window = CopyPending(_segmentSamples);
            var cut = AudioSegmenter.FindQuietestPoint(window,
                _segmentSamples - AudioSegmenter.SilenceSearchSeconds * AudioChunk.SampleRate, _segmentSamples);
            Emit(window.AsMemory(0, cut));
            Consume(cut);
        }
    }

    internal void Complete()
    {
        if (_pendingSamples > 0) Emit(CopyPending(_pendingSamples));
        _pending.Clear();
        _pendingSamples = 0;
    }

    private void Emit(ReadOnlyMemory<float> segment) { _segments.Add(segment); segmentReady(segment); }

    private float[] CopyPending(int count)
    {
        var result = new float[count];
        var offset = 0;
        foreach (var chunk in _pending)
        {
            var take = Math.Min(chunk.Length, count - offset);
            chunk.Span[..take].CopyTo(result.AsSpan(offset));
            offset += take;
            if (offset == count) break;
        }
        return result;
    }

    private void Consume(int count)
    {
        _pendingSamples -= count;
        var consumed = 0;
        while (consumed < _pending.Count && count >= _pending[consumed].Length)
        {
            count -= _pending[consumed].Length;
            consumed++;
        }
        _pending.RemoveRange(0, consumed);
        if (count > 0) _pending[0] = _pending[0][count..];
    }
}
