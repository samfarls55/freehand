using Freehand.Abstractions;

namespace Freehand.Core;

/// <summary>
/// Splits a long recording into pieces the encoder can actually process.
/// </summary>
/// <remarks>
/// <para>
/// Parakeet's exported encoder carries a fixed relative-position table sized for 5000
/// frames. At 80 ms per frame that is <b>400 seconds</b>, and past it inference does not
/// degrade — it throws:
/// </para>
/// <code>
/// Attempting to broadcast an axis by a dimension other than 1. 126 by 5126
/// </code>
/// <para>
/// Native temporary memory grows with input length. Short segments bound the peak and
/// let dictation decode completed portions while the microphone is still recording.
/// </para>
/// <para>
/// Cuts are placed at the quietest point in a search window rather than at a fixed offset,
/// so a split lands between words instead of through one.
/// </para>
/// </remarks>
public static class AudioSegmenter
{
    /// <summary>The hard limit imposed by the encoder's position table, in seconds.</summary>
    public const int EncoderCeilingSeconds = 400;

    /// <summary>
    /// Bounds native temporary memory and the audio still to decode after key release.
    /// </summary>
    public const int MaxSegmentSeconds = 15;

    /// <summary>
    /// How far back from the cut point to look for a quiet moment. A cut is placed at the
    /// lowest-energy window found here, so it lands in a pause rather than mid-word.
    /// </summary>
    public const int SilenceSearchSeconds = 3;

    private const int MaxSegmentSamples = MaxSegmentSeconds * AudioChunk.SampleRate;
    private const int SearchSamples = SilenceSearchSeconds * AudioChunk.SampleRate;

    /// <summary>A 200 ms window favors pauses over brief low-energy sounds within a word.</summary>
    private const int EnergyWindow = AudioChunk.SampleRate / 5;

    /// <summary>
    /// Splits <paramref name="samples"/> into segments no longer than
    /// <see cref="MaxSegmentSeconds"/>.
    /// </summary>
    /// <returns>
    /// One segment when the input is already short enough — the common case for dictation,
    /// and it allocates nothing.
    /// </returns>
    public static IReadOnlyList<ReadOnlyMemory<float>> Split(ReadOnlyMemory<float> samples)
    {
        if (samples.Length <= MaxSegmentSamples) return [samples];

        var segments = new List<ReadOnlyMemory<float>>();
        var start = 0;

        while (start < samples.Length)
        {
            var remaining = samples.Length - start;
            if (remaining <= MaxSegmentSamples)
            {
                segments.Add(samples[start..]);
                break;
            }

            var idealEnd = start + MaxSegmentSamples;
            var cut = FindQuietestPoint(samples.Span, idealEnd - SearchSamples, idealEnd);

            // Never let a degenerate search produce a zero-length segment and loop forever.
            if (cut <= start) cut = idealEnd;

            segments.Add(samples[start..cut]);
            start = cut;
        }

        return segments;
    }

    /// <summary>
    /// Finds the lowest-energy window in <c>[from, to)</c> and returns its midpoint.
    /// </summary>
    internal static int FindQuietestPoint(ReadOnlySpan<float> samples, int from, int to)
    {
        from = Math.Max(from, 0);
        to = Math.Min(to, samples.Length);
        if (to - from < EnergyWindow) return to;

        var quietestAt = from;
        var quietest = double.MaxValue;

        for (var offset = from; offset + EnergyWindow <= to; offset += EnergyWindow)
        {
            double energy = 0;
            for (var i = offset; i < offset + EnergyWindow; i++) energy += Math.Abs(samples[i]);

            if (energy < quietest)
            {
                quietest = energy;
                quietestAt = offset;
            }
        }

        return quietestAt + (EnergyWindow / 2);
    }
}
